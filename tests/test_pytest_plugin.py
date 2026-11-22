import json
from pathlib import Path

import pytest
from coverage import CoverageData

pytest_plugins = ["pytester"]

SYNC_ONLY = ("-p", "no:asyncio")

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
from contextlib import contextmanager
from runpy import run_path

import pytest
from coverage import Coverage
from coverage_wasm import GuestCoverage, snapshot


@pytest.fixture
def measured_guest(wasm_coverage, tmp_path):
    @contextmanager
    def start(guest: GuestCoverage | None):
        file = {str(guest)!r}
        if guest is None:
            yield run_path(file)["decide"]
            return
        collector = Coverage(
            data_file=tmp_path / ".coverage.guest",
            config_file=False,
            branch=guest.branch,
            source=guest.source or None,
            include=guest.include,
            omit=guest.omit,
            context=guest.context,
        )
        with collector.collect():
            yield run_path(file)["decide"]
        guest.save(snapshot(collector))

    with wasm_coverage.launch(start) as decide:
        yield decide
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

    result = pytester.runpytest_inprocess(*SYNC_ONLY, "--cov=src", "--cov-report=html")

    result.assert_outcomes(passed=1)
    index = reports / "html" / "index.html"
    assert "decision.py" in index.read_text(encoding="utf-8")
    output = result.stdout.str()
    assert "Wasm coverage enabled" in output
    assert "Wasm coverage collected from 1 test" in output
    assert "Coverage HTML written to dir reports/html" in output
    data = CoverageData(basename=str(reports / ".coverage"))
    data.read()
    assert data.contexts_by_lineno(str(source))[3] == ["test_guest.py::test_guest"]
    arcs = data.arcs(str(source))
    assert arcs is not None
    assert (2, 3) in arcs
    assert (2, 4) not in arcs


def test_pytest_cov_applies_configured_fail_under_to_guest_data(
    pytester: pytest.Pytester,
) -> None:
    make_guest_project(pytester, minimum=100)

    result = pytester.runpytest_inprocess(*SYNC_ONLY, "--cov=src", "--cov-report=html")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    assert "fail-under=100" in result.stdout.str()
    assert "Wasm coverage collected from 1 test" in result.stdout.str()
    assert (pytester.path / "reports" / "html" / "index.html").is_file()


@pytest.mark.parametrize(
    "options",
    [[], ["--cov", "--no-cov"], ["--collect-only"]],
    ids=["plain", "no-cov", "collect-only"],
)
def test_without_coverage_leaves_artifacts_unmodified(
    pytester: pytest.Pytester, options: list[str]
) -> None:
    pytester.makepyfile(
        """\
from pathlib import Path


def test_guest(wasm_coverage):
    assert not wasm_coverage.enabled
    marker = object()

    def start(guest):
        assert guest is None
        return marker

    assert wasm_coverage.launch(start) is marker
    wasm_coverage.add_file(Path("missing.coverage"))
"""
    )
    html = pytester.path / "htmlcov"
    html.mkdir()
    index = html / "index.html"
    index.write_text("existing report", encoding="utf-8")
    data = pytester.path / ".coverage"
    data.write_bytes(b"existing report data")

    result = pytester.runpytest_inprocess(*SYNC_ONLY, *options)

    assert result.ret == pytest.ExitCode.OK
    assert index.read_text(encoding="utf-8") == "existing report"
    assert data.read_bytes() == b"existing report data"
    assert "Wasm coverage" not in result.stdout.str()


def test_pytest_cov_combines_host_and_wasm_shards(pytester: pytest.Pytester) -> None:
    source = make_guest_project(pytester)
    host_source = source.with_name("host_only.py")
    host_source.write_text("VALUE = 'host'\n", encoding="utf-8")
    pytester.makepyfile(
        test_host="""\
from pathlib import Path
from runpy import run_path

import pytest


def test_host():
    assert run_path("src/host_only.py")["VALUE"] == "host"


@pytest.mark.no_cover
def test_guest_skips_marked_cases(wasm_coverage):
    assert not wasm_coverage.enabled
    wasm_coverage.add_file(Path("missing.coverage"))


def test_guest_skips_no_cover_fixture(no_cover, wasm_coverage):
    assert not wasm_coverage.enabled
    wasm_coverage.add_file(Path("missing.coverage"))
"""
    )

    result = pytester.runpytest_inprocess(
        *SYNC_ONLY,
        "--cov=src",
        "--cov-branch",
        "--cov-context=test",
        "--cov-report=html",
    )

    result.assert_outcomes(passed=4)
    reports = pytester.path / "reports"
    index = (reports / "html" / "index.html").read_text(encoding="utf-8")
    assert "decision.py" in index
    assert "host_only.py" in index
    assert list(reports.glob(".coverage*")) == [reports / ".coverage"]
    data = CoverageData(basename=str(reports / ".coverage"))
    data.read()
    assert data.lines(str(host_source)) == [1]
    assert data.contexts_by_lineno(str(source))[3] == ["test_guest.py::test_guest"]
    assert "Wasm coverage collected from 1 test" in result.stdout.str()


def test_guest_snapshot_validation(pytester: pytest.Pytester) -> None:
    application = pytester.makepyfile(application="VALUE = 42")
    (pytester.path / "invalid.coverage").write_bytes(b"not SQLite")
    empty = CoverageData(basename=pytester.path / "empty.coverage")
    empty.add_arcs({})
    empty.write()
    empty.close(force=True)
    unexecuted = CoverageData(basename=pytester.path / "unexecuted.coverage")
    unexecuted.add_arcs({})
    unexecuted.touch_file(str(application))
    unexecuted.write()
    unexecuted.close(force=True)
    lines = CoverageData(basename=pytester.path / "lines.coverage")
    lines.add_lines({str(application): [1]})
    lines.write()
    lines.close(force=True)

    pytester.makepyfile(
        test_snapshots="""\
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("name", "error", "message"),
    [
        ("invalid", ValueError, "expects a native Coverage.py"),
        ("empty", RuntimeError, "snapshot has no measured files"),
        ("lines", ValueError, "must use the same branch coverage mode"),
    ],
)
def test_invalid_snapshot(wasm_coverage, name, error, message):
    with pytest.raises(error, match=message):
        wasm_coverage.add_file(Path(f"{name}.coverage"))


def test_launcher_can_ignore_empty_snapshot(wasm_coverage):
    def start(guest):
        guest.save(Path("empty.coverage").read_bytes(), allow_empty=True)

    with pytest.warns(pytest.PytestWarning, match="No Python files measured"):
        wasm_coverage.launch(start)


def test_unexecuted_source_does_not_count_as_measured(wasm_coverage):
    wasm_coverage.add_file(Path("unexecuted.coverage"))
"""
    )

    result = pytester.runpytest_inprocess(*SYNC_ONLY, "--cov=.", "--cov-branch")

    result.assert_outcomes(passed=5, warnings=0)
    assert "Wasm coverage collected from 0 tests" in result.stdout.str()
    data = CoverageData(basename=pytester.path / ".coverage")
    data.read()
    assert data.lines(str(application)) == []


def test_collect_only_does_not_enable_wasm_coverage(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_guest(wasm_coverage): raise AssertionError")

    result = pytester.runpytest_inprocess(*SYNC_ONLY, "--cov", "--collect-only")

    assert result.ret == pytest.ExitCode.OK
    assert "1 test collected" in result.stdout.str()
    assert "Wasm coverage" not in result.stdout.str()


def test_missing_host_collector_is_reported(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """\
import pytest
from coverage import Coverage


@pytest.fixture
def stopped_host_collector():
    collector = Coverage.current()
    assert collector is not None
    collector.stop()
    try:
        yield
    finally:
        collector.start()


def test_guest(stopped_host_collector, wasm_coverage):
    raise AssertionError("the guest should never start")
"""
    )

    result = pytester.runpytest_inprocess(*SYNC_ONLY, "--cov=.", "--cov-report=")

    result.assert_outcomes(errors=1)
    assert "pytest-cov did not start its Coverage.py collector" in result.stdout.str()


def test_workerd_bundle_staging_keeps_original_bundle_clean(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyfile(
        """\
from pathlib import Path

import pytest


def test_covered_bundle(wasm_coverage, tmp_path):
    bundle = tmp_path / "bundle"
    modules = bundle / "python_modules"
    modules.mkdir(parents=True)
    (bundle / "entrypoint.py").write_text("VALUE = 42", encoding="utf-8")

    staged = wasm_coverage.workerd_bundle(bundle)

    assert staged != bundle
    assert staged.name == bundle.name
    assert (staged / "entrypoint.py").read_bytes() == (bundle / "entrypoint.py").read_bytes()
    assert list(modules.iterdir()) == []
    startup = (staged / "python_modules" / "coverage_wasm.pth").read_text(encoding="utf-8")
    assert "/session/metadata/**" in startup
    assert "/session/metadata/python_modules/**" in startup
    assert (staged / "python_modules" / "coverage").is_dir()


@pytest.mark.parametrize("module_path", ["absolute", "../outside"])
def test_rejects_modules_outside_bundle(wasm_coverage, tmp_path, module_path):
    path = tmp_path if module_path == "absolute" else Path(module_path)
    with pytest.raises(ValueError, match="python_modules must be relative"):
        wasm_coverage.workerd_bundle(tmp_path, python_modules=path)


def test_install_into_an_existing_test_only_bundle(wasm_coverage, tmp_path):
    wasm_coverage.install_workerd(tmp_path, include=["/guest/application.py"])
    startup = (tmp_path / "coverage_wasm.pth").read_text(encoding="utf-8")
    assert "/guest/application.py" in startup


@pytest.mark.no_cover
def test_uncovered_bundle_uses_original_path(wasm_coverage, tmp_path):
    assert wasm_coverage.workerd_bundle(tmp_path) == tmp_path
    wasm_coverage.install_workerd(tmp_path, include=["/guest/application.py"])
    assert list(tmp_path.iterdir()) == []
"""
    )

    result = pytester.runpytest_inprocess(*SYNC_ONLY, "--cov", "--cov-report=")

    result.assert_outcomes(passed=5, warnings=0)
    assert "Wasm coverage collected from 0 tests" in result.stdout.str()


def test_xdist_worker_is_rejected_with_serial_command(
    pytester: pytest.Pytester,
) -> None:
    pytest.importorskip("xdist")
    pytester.makepyfile(
        """\
def test_guest(wasm_coverage):
    wasm_coverage.launch(lambda _: None)
"""
    )

    result = pytester.runpytest_subprocess(
        *SYNC_ONLY, "--cov=.", "--cov-report=", "-n", "1"
    )

    result.assert_outcomes(failed=1)
    assert "coverage-wasm requires serial pytest; use -n 0" in result.stdout.str()
