from importlib.util import find_spec
from pathlib import Path

import pytest
from coverage import CoverageData

from coverage_wasm import GuestCoverage
from coverage_wasm.wasi import grant_paths, run

pytest_plugins = ["pytester"]
pytestmark = pytest.mark.skipif(
    find_spec("wasi_python") is None, reason="Requires wasi-python"
)


@pytest.fixture
def guest_capture(tmp_path: Path) -> tuple[GuestCoverage, Path]:
    shard = tmp_path / ".coverage.guest"

    def save(snapshot: bytes, _allow_empty: bool) -> None:
        shard.write_bytes(snapshot)

    return GuestCoverage("wasi-test", True, [], None, None, save), shard


@pytest.mark.parametrize("mode", ["plain", "inferred", "configured"])
def test_wasi_target_runs_script_and_collects_when_requested(
    pytester: pytest.Pytester, mode: str
) -> None:
    source = pytester.path / "src" / "shipping.py"
    source.parent.mkdir()
    source.write_text(
        """\
from os import environ

if int(input()) >= int(environ['FREE_THRESHOLD']):
    print(0)
else:
    print(500)
""",
        encoding="utf-8",
    )
    configuration = """\
[tool.coverage.run]
branch = true
data_file = "reports/.coverage"

[tool.coverage.html]
directory = "reports/html"
"""
    if mode == "configured":
        configuration += '\n[tool.coverage.paths]\nsource = ["src", "/app"]\n'
    pytester.makepyprojecttoml(configuration)
    pytester.makepyfile(
        test_shipping="""\
from pathlib import Path

from wasi_python import Grant

from coverage_wasm import targets


def test_shipping(wasm_coverage):
    target = targets.wasi(
        ["/app/shipping.py"],
        grants=[Grant(Path("src").resolve(), "/app")],
        env={"FREE_THRESHOLD": "5000"},
        stdin=b"5000\\n",
    )
    with wasm_coverage(target) as result:
        assert result.exit_code == 0, result.stderr.decode()
        assert result.stdout == b"0\\n"
"""
    )

    if mode == "plain":
        result = pytester.runpytest_inprocess()
    else:
        result = pytester.runpytest_subprocess("--cov=src", "--cov-report=html")

    result.assert_outcomes(passed=1)
    reports = pytester.path / "reports"
    if mode == "plain":
        assert not reports.exists()
        return

    index = reports / "html" / "index.html"
    assert "shipping.py" in index.read_text(encoding="utf-8")
    data = CoverageData(basename=str(reports / ".coverage"))
    data.read()
    assert data.measured_files() == {str(source)}
    assert data.contexts_by_lineno(str(source))[4] == [
        "test_shipping.py::test_shipping"
    ]
    arcs = data.arcs(str(source))
    assert arcs is not None
    assert (3, 4) in arcs
    assert (3, 6) not in arcs


def test_wasi_coverage_uses_the_deepest_mount_and_the_host_root(
    tmp_path: Path, guest_capture: tuple[GuestCoverage, Path]
) -> None:
    from wasi_python import Grant

    guest, shard = guest_capture
    root = tmp_path / "root"
    mounted = tmp_path / "mounted"
    for directory in (root, mounted):
        directory.mkdir(mode=0o700)
    entry = root / "main.py"
    entry.write_text("from fee import FEE\nprint(FEE)\n", encoding="utf-8")
    fee = mounted / "fee.py"
    fee.write_text("FEE = 500\n", encoding="utf-8")
    grants = [Grant(mounted, "/app/rates")]

    result = run(
        ["/main.py"],
        root=root,
        grants=grants,
        import_path=["/app/rates"],
        guest=guest,
        paths=grant_paths(grants, root),
    )

    assert result.exit_code == 0, result.stderr.decode()
    assert result.stdout == b"500\n"
    data = CoverageData(basename=str(shard))
    data.read()
    assert data.measured_files() == {str(entry.resolve()), str(fee.resolve())}


@pytest.mark.parametrize("has_aliases", [False, True], ids=["native", "unmapped"])
def test_wasi_preserves_source_names_without_matching_aliases(
    tmp_path: Path, guest_capture: tuple[GuestCoverage, Path], has_aliases: bool
) -> None:
    from wasi_python import Grant

    guest, shard = guest_capture
    (tmp_path / "main.py").write_text("print(500)\n", encoding="utf-8")
    paths = grant_paths([Grant(tmp_path, "/unrelated")], None) if has_aliases else None

    result = run(
        ["/app/main.py"],
        grants=[Grant(tmp_path, "/app")],
        guest=guest,
        paths=paths,
    )

    assert result.exit_code == 0, result.stderr.decode()
    data = CoverageData(basename=str(shard))
    data.read()
    assert data.lines("/app/main.py") == [1]


@pytest.mark.parametrize("argv", [[], [""], ["-c", "pass"]])
def test_instrumented_wasi_requires_a_script_path(
    argv: list[str], guest_capture: tuple[GuestCoverage, Path]
) -> None:
    guest, shard = guest_capture

    with pytest.raises(ValueError, match="expects a Python script path"):
        run(argv, guest=guest)

    assert not shard.exists()


@pytest.mark.parametrize("status", [0, 17], ids=["success", "failure"])
def test_wasi_reports_abrupt_exits_without_a_snapshot(
    tmp_path: Path, guest_capture: tuple[GuestCoverage, Path], status: int
) -> None:
    from wasi_python import Grant

    guest, shard = guest_capture
    (tmp_path / "main.py").write_text(
        f"import os\nos._exit({status})\n", encoding="utf-8"
    )
    grants = [Grant(tmp_path, "/app")]

    if status == 0:
        with pytest.raises(RuntimeError, match="did not produce a coverage file"):
            run(["/app/main.py"], grants=grants, guest=guest)
    else:
        result = run(["/app/main.py"], grants=grants, guest=guest)
        assert result.exit_code == status

    assert not shard.exists()
