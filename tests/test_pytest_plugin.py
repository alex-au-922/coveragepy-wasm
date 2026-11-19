import json
from importlib.util import find_spec
from pathlib import Path

import pytest
from coverage import CoverageData

pytest_plugins = ["pytester"]

DECISION = """\
def decide(take_branch):
    if take_branch:
        return "taken"
    return "unused"
"""


def make_guest_project(pytester: pytest.Pytester, *, minimum: int = 0) -> Path:
    source = pytester.path / "src" / "decision.py"
    guest = pytester.path / "guest" / "decision.py"
    for path in (source, guest):
        path.parent.mkdir()
        path.write_text(DECISION, encoding="utf-8")

    (pytester.path / "pyproject.toml").write_text(
        f"""\
[tool.coverage.run]
branch = true
data_file = "reports/.coverage"

[tool.coverage.paths]
source = ["src", {json.dumps(guest.parent.as_posix(), ensure_ascii=False)}]

[tool.coverage.report]
fail_under = {minimum}

[tool.coverage.html]
directory = "reports/html"
show_contexts = true
""",
        encoding="utf-8",
    )
    pytester.makeconftest(
        f"""\
from runpy import run_path

import pytest
from coverage import Coverage


@pytest.fixture
def measured_guest(wasm_coverage, tmp_path):
    guest = {str(guest)!r}
    shard = tmp_path / ".coverage.guest"
    coverage = Coverage(
        data_file=shard,
        config_file=False,
        branch=True,
        include=[guest],
        context=wasm_coverage.context,
    )
    with coverage.collect():
        decide = run_path(guest)["decide"]
        yield decide
    coverage.save()
    wasm_coverage.add_file(shard)
"""
    )
    pytester.makepyfile(
        test_guest="""\
def test_guest(measured_guest):
    assert measured_guest(True) == "taken"
"""
    )
    return source


def test_installed_plugin_reports_wasm_with_configured_paths_and_context(
    pytester: pytest.Pytester,
) -> None:
    source = make_guest_project(pytester)
    reports = pytester.path / "reports"
    reports.mkdir()
    host_data = reports / ".coverage"
    host_data.write_bytes(b"existing host data")

    result = pytester.runpytest_inprocess()

    result.assert_outcomes(passed=1)
    index = reports / "html" / "index.html"
    assert "decision.py" in index.read_text(encoding="utf-8")
    result.stdout.fnmatch_lines([f"Wasm coverage HTML: {index}"])
    assert host_data.read_bytes() == b"existing host data"
    data = CoverageData(basename=str(reports / ".coverage-wasm"))
    data.read()
    assert data.contexts_by_lineno(str(source))[3] == ["test_guest.py::test_guest"]
    arcs = data.arcs(str(source))
    assert arcs is not None
    assert (2, 3) in arcs
    assert (2, 4) not in arcs


def test_installed_plugin_enforces_coverage_fail_under(
    pytester: pytest.Pytester,
) -> None:
    make_guest_project(pytester, minimum=100)

    result = pytester.runpytest_inprocess()

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*Wasm coverage*% is below 100%*"])
    assert (pytester.path / "reports" / "html" / "index.html").is_file()


def test_disabled_plugin_ignores_guest_shard(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """\
from pathlib import Path


def test_guest(wasm_coverage):
    wasm_coverage.add_file(Path("missing.coverage"))
"""
    )

    result = pytester.runpytest_inprocess("--no-wasm-coverage")

    result.assert_outcomes(passed=1)
    assert not (pytester.path / "htmlcov").exists()
    assert "Wasm coverage HTML:" not in result.stdout.str()


@pytest.mark.parametrize("option", [None, "--collect-only"])
def test_plugin_without_wasm_leaves_artifacts_unmodified(
    pytester: pytest.Pytester, option: str | None
) -> None:
    if option is None:
        pytester.makepyfile("def test_plain(): pass")
        html = pytester.path / "htmlcov"
    else:
        make_guest_project(pytester)
        html = pytester.path / "reports" / "html"
    html.mkdir(parents=True)
    index = html / "index.html"
    index.write_text("existing report", encoding="utf-8")
    data = html.parent / ".coverage-wasm"
    data.write_bytes(b"existing report data")

    result = pytester.runpytest_inprocess(*([] if option is None else [option]))

    assert result.ret == pytest.ExitCode.OK
    assert index.read_text(encoding="utf-8") == "existing report"
    assert data.read_bytes() == b"existing report data"
    assert "Wasm coverage HTML:" not in result.stdout.str()


@pytest.mark.skipif(find_spec("pytest_cov") is None, reason="Requires pytest-cov")
def test_pytest_cov_combines_host_and_wasm_shards(pytester: pytest.Pytester) -> None:
    source = make_guest_project(pytester)
    host_source = source.with_name("host_only.py")
    host_source.write_text("VALUE = 'host'\n", encoding="utf-8")
    pytester.makepyfile(
        test_host="""\
from runpy import run_path


def test_host():
    assert run_path("src/host_only.py")["VALUE"] == "host"
"""
    )

    result = pytester.runpytest_inprocess(
        "--cov=src", "--cov-branch", "--cov-report=html"
    )

    result.assert_outcomes(passed=2)
    reports = pytester.path / "reports"
    index = (reports / "html" / "index.html").read_text(encoding="utf-8")
    assert "decision.py" in index
    assert "host_only.py" in index
    assert not (reports / ".coverage-wasm").exists()
    data = CoverageData(basename=str(reports / ".coverage"))
    data.read()
    assert data.lines(str(host_source)) == [1]
    assert data.contexts_by_lineno(str(source))[3] == ["test_guest.py::test_guest"]
