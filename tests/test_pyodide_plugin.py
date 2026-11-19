from importlib.util import find_spec
from pathlib import Path
from shutil import which

import pytest
from coverage import CoverageData

pytest_plugins = ("pytester",)
pytestmark = pytest.mark.skipif(
    find_spec("pytest_pyodide") is None, reason="Requires pytest-pyodide"
)

DECISION = """\
def decide(take_branch):
    if take_branch:
        return "taken"
    return "unused"
"""
PYTEST_OPTIONS = """\
[tool.pytest.ini_options]
asyncio_default_fixture_loop_scope = "function"
"""


@pytest.fixture
def node_options(pytestconfig: pytest.Config) -> tuple[str, str]:
    dist_dir = pytestconfig.rootpath / str(pytestconfig.getoption("--dist-dir"))
    if not (dist_dir / "pyodide-lock.json").is_file() or which("node") is None:
        pytest.skip("Requires Node and a Pyodide distribution (--dist-dir)")
    return "--runtime=node", f"--dist-dir={dist_dir}"


def test_installed_plugin_collects_existing_pyodide_fixtures(
    pytester: pytest.Pytester, node_options: tuple[str, str]
) -> None:
    pytester.makepyprojecttoml(
        PYTEST_OPTIONS
        + """
[tool.coverage.run]
branch = true

[tool.coverage.paths]
source = [".", "/project"]
"""
    )
    program = pytester.makepyfile(decision=DECISION)
    pytester.makepyfile(
        test_guest='''\
from pathlib import Path

import pytest


@pytest.mark.parametrize("take_branch", [True, False], ids=["take", "skip"])
def test_guest(selenium, take_branch):
    source = Path(__file__).with_name("decision.py").read_text()
    assert selenium.run(f"""
from pathlib import Path
from runpy import run_path
from sys import platform

assert platform == 'emscripten'
path = Path('/project/decision.py')
path.parent.mkdir(exist_ok=True)
path.write_text({source!r})
run_path(str(path))['decide']({take_branch!r})
""") == ("taken" if take_branch else "unused")
'''
    )

    result = pytester.runpytest_subprocess(*node_options, "-q")
    result.assert_outcomes(passed=2)

    data = CoverageData(basename=str(pytester.path / ".coverage-wasm"))
    data.read()
    (filename,) = data.measured_files()
    assert Path(filename).resolve() == program.resolve()
    contexts = data.contexts_by_lineno(filename)
    assert contexts[3] == ["test_guest.py::test_guest[node-take]"]
    assert contexts[4] == ["test_guest.py::test_guest[node-skip]"]
    report = pytester.path / "htmlcov" / "index.html"
    assert "decision.py" in report.read_text(encoding="utf-8")


@pytest.mark.skipif(find_spec("pytest_cov") is None, reason="Requires pytest-cov")
def test_pytest_cov_maps_source_directory_into_pyodide(
    pytester: pytest.Pytester, node_options: tuple[str, str]
) -> None:
    pytester.makepyprojecttoml(
        PYTEST_OPTIONS
        + """
[tool.coverage.paths]
source = ["src", "/app"]
"""
    )
    program = pytester.path / "src" / "decision.py"
    program.parent.mkdir()
    program.write_text(DECISION, encoding="utf-8")
    pytester.makepyfile(
        test_guest='''\
from pathlib import Path
from runpy import run_path


def test_guest(selenium_standalone):
    source = Path("src/decision.py").read_text()
    assert selenium_standalone.run(f"""
from pathlib import Path
from runpy import run_path

path = Path('/app/decision.py')
path.parent.mkdir(exist_ok=True)
path.write_text({source!r})
run_path(str(path))['decide'](True)
""") == "taken"


def test_host():
    assert run_path("src/decision.py")["decide"](False) == "unused"
'''
    )

    result = pytester.runpytest_subprocess(
        *node_options, "--cov=src", "--cov-branch", "--cov-report=html", "-q"
    )
    result.assert_outcomes(passed=2)
    assert "No data was collected" not in result.stdout.str()

    data = CoverageData(basename=str(pytester.path / ".coverage"))
    data.read()
    (filename,) = data.measured_files()
    assert Path(filename).resolve() == program.resolve()
    assert {(2, 3), (2, 4)} <= set(data.arcs(filename) or [])
    assert data.contexts_by_lineno(filename)[3] == ["test_guest.py::test_guest[node]"]
    assert "decision.py" in (pytester.path / "htmlcov/index.html").read_text(
        encoding="utf-8"
    )


def test_empty_pyodide_coverage_is_reported(
    pytester: pytest.Pytester, node_options: tuple[str, str]
) -> None:
    pytester.makepyprojecttoml(
        PYTEST_OPTIONS
        + """
[tool.coverage.run]
include = ["*/decision.py"]
"""
    )
    pytester.makepyfile(
        test_guest="""\
def test_guest(selenium_standalone):
    assert selenium_standalone.run("21 + 21") == 42
"""
    )

    result = pytester.runpytest_subprocess(*node_options, "-q")
    result.assert_outcomes(passed=1, warnings=1)
    assert "No Python files" in result.stdout.str()
    assert "test_guest.py::test_guest[node]" in result.stdout.str()
    assert not (pytester.path / ".coverage-wasm").exists()


def test_existing_pyodide_coverage_decorator_can_opt_out(
    pytester: pytest.Pytester, node_options: tuple[str, str]
) -> None:
    pytester.makepyprojecttoml(PYTEST_OPTIONS)
    pytester.makepyfile(
        test_guest="""\
from pytest_pyodide.decorator import run_in_pyodide_coverage


@run_in_pyodide_coverage(pytest_assert_rewrites=False)
def test_guest(selenium_standalone):
    assert sum([20, 22]) == 42
"""
    )

    result = pytester.runpytest_subprocess(*node_options, "--no-wasm-coverage", "-q")
    result.assert_outcomes(passed=1)
    (shard,) = pytester.path.glob(".coverage.emscripten.*")
    data = CoverageData(basename=str(shard))
    data.read()
    assert any(path.endswith("test_guest.py") for path in data.measured_files())
    assert not (pytester.path / ".coverage-wasm").exists()
