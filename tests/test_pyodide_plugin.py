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
addopts = "--cov --cov-report=html"

[tool.coverage.run]
branch = true
include = ["*/decision.py"]

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

    result = pytester.runpytest_subprocess(*node_options, "-v")
    result.assert_outcomes(passed=2)
    output = result.stdout.str()
    assert "Wasm coverage enabled" in output
    assert (
        "Wasm coverage collected from 2 tests\n"
        "  test_guest.py::test_guest[node-skip]\n"
        "  test_guest.py::test_guest[node-take]"
    ) in output

    data = CoverageData(basename=str(pytester.path / ".coverage"))
    data.read()
    (filename,) = data.measured_files()
    assert Path(filename).resolve() == program.resolve()
    contexts = data.contexts_by_lineno(filename)
    assert contexts[3] == ["test_guest.py::test_guest[node-take]"]
    assert contexts[4] == ["test_guest.py::test_guest[node-skip]"]
    report = pytester.path / "htmlcov" / "index.html"
    assert "decision.py" in report.read_text(encoding="utf-8")


def test_pytest_cov_maps_source_directories_and_modules_into_pyodide(
    pytester: pytest.Pytester, node_options: tuple[str, str]
) -> None:
    pytester.makepyprojecttoml(
        PYTEST_OPTIONS
        + """
[tool.coverage.paths]
app = ["src/engine", "/app"]
project = [".", "/checkout"]
external = ["vendor", "/vendor"]
"""
    )
    program = pytester.path / "src" / "engine" / "decision.py"
    program.parent.mkdir(parents=True)
    program.write_text(DECISION, encoding="utf-8")
    companion = pytester.makepyfile(companion=DECISION)
    (pytester.path / "vendor").mkdir()
    pytester.makepyfile(
        test_guest='''\
from pathlib import Path
from runpy import run_path

import companion


def test_guest(selenium_standalone):
    for local, guest in (
        ("src/engine/decision.py", "/app/decision.py"),
        ("companion.py", "/checkout/companion.py"),
    ):
        source = Path(local).read_text()
        assert selenium_standalone.run(f"""
from pathlib import Path
from runpy import run_path

path = Path({guest!r})
path.parent.mkdir(exist_ok=True)
path.write_text({source!r})
run_path(str(path))['decide'](True)
""") == "taken"


def test_host():
    assert run_path("src/engine/decision.py")["decide"](False) == "unused"
    assert companion.decide(False) == "unused"
'''
    )

    result = pytester.runpytest_subprocess(
        *node_options,
        "--cov=src",
        "--cov=companion",
        "--cov-branch",
        "--cov-fail-under=100",
        "--cov-report=html",
        "-q",
    )
    result.assert_outcomes(passed=2)
    assert "No data was collected" not in result.stdout.str()

    data = CoverageData(basename=str(pytester.path / ".coverage"))
    data.read()
    files = {Path(filename).resolve(): filename for filename in data.measured_files()}
    assert set(files) == {program.resolve(), companion.resolve()}
    report = (pytester.path / "htmlcov/index.html").read_text(encoding="utf-8")
    for source, filename in files.items():
        assert {(2, 3), (2, 4)} <= set(data.arcs(filename) or [])
        assert data.contexts_by_lineno(filename)[3] == [
            "test_guest.py::test_guest[node]"
        ]
        assert source.name in report


def test_empty_pyodide_coverage_is_reported(
    pytester: pytest.Pytester, node_options: tuple[str, str]
) -> None:
    pytester.makepyprojecttoml(
        PYTEST_OPTIONS
        + """
[tool.coverage.run]
include = ["*/test_guest.py"]
"""
    )
    pytester.makepyfile(
        test_guest="""\
def test_guest(selenium_standalone):
    assert selenium_standalone.run("21 + 21") == 42
"""
    )

    result = pytester.runpytest_subprocess(*node_options, "--cov", "-q")
    result.assert_outcomes(passed=1, warnings=1)
    assert "No Python files" in result.stdout.str()
    assert "test_guest.py::test_guest[node]" in result.stdout.str()
    assert "Wasm coverage collected from 0 tests" in result.stdout.str()
    data = CoverageData(basename=str(pytester.path / ".coverage"))
    data.read()
    assert data.measured_files() == {str(pytester.path / "test_guest.py")}


def test_custom_launcher_maps_source_while_ignoring_empty_alias_groups(
    pytester: pytest.Pytester, node_options: tuple[str, str]
) -> None:
    pytester.makepyprojecttoml(PYTEST_OPTIONS)
    program = pytester.path / "src" / "decision.py"
    program.parent.mkdir()
    program.write_text(DECISION, encoding="utf-8")
    pytester.makepyfile(
        test_guest='''\
from pathlib import Path

from coverage_wasm.pyodide import start_pyodide_coverage


def test_guest(selenium_standalone_noload, wasm_coverage):
    runner = selenium_standalone_noload
    runner.load_pyodide()
    runner.initialize_pyodide()
    program = Path("src/decision.py").resolve()
    root = program.parent.as_posix()

    def start(guest):
        assert guest.source == []
        assert guest.include == [f"{root}/**", "src/**"]
        return start_pyodide_coverage(runner, guest)

    finish = wasm_coverage.launch(
        start, source_aliases={"unused": [], "app": ["src", root]}
    )
    try:
        assert runner.run(f"""
from pathlib import Path
from runpy import run_path

path = Path({program.as_posix()!r})
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text({program.read_text(encoding='utf-8')!r})
run_path(str(path))['decide'](True)
""") == "taken"
    finally:
        finish()
'''
    )

    result = pytester.runpytest_subprocess(
        *node_options, "--cov=src", "--cov-branch", "-q"
    )
    result.assert_outcomes(passed=1)
    assert "Wasm coverage collected from 1 test" in result.stdout.str()
    data = CoverageData(basename=str(pytester.path / ".coverage"))
    data.read()
    assert data.contexts_by_lineno(str(program))[3] == [
        "test_guest.py::test_guest[node]"
    ]


def test_explicit_pyodide_context_works_with_and_without_automatic_fixture(
    pytester: pytest.Pytester, node_options: tuple[str, str]
) -> None:
    pytester.makepyprojecttoml(
        PYTEST_OPTIONS
        + """
[tool.coverage.run]
branch = true
include = ["*/decision.py"]

[tool.coverage.paths]
source = [".", "/project"]
"""
    )
    program = pytester.makepyfile(decision=DECISION)
    pytester.makepyfile(
        test_guest='''\
from pathlib import Path

import pytest
from coverage_wasm import targets

SOURCE = Path("decision.py").read_text(encoding="utf-8")


def decide(runner, take_branch):
    return runner.run(f"""
from pathlib import Path
from runpy import run_path

module = Path('/project/decision.py')
module.parent.mkdir(exist_ok=True)
module.write_text({SOURCE!r}, encoding='utf-8')
run_path(str(module))['decide']({take_branch!r})
""")


def test_existing_scope(selenium_standalone, wasm_coverage):
    assert decide(selenium_standalone, True) == "taken"
    with wasm_coverage(targets.pyodide(selenium_standalone)) as runner:
        assert runner is selenium_standalone


def test_custom_scope(selenium_standalone_noload, wasm_coverage):
    selenium_standalone_noload.load_pyodide()
    selenium_standalone_noload.initialize_pyodide()
    with wasm_coverage(targets.pyodide(selenium_standalone_noload)) as runner:
        assert decide(runner, False) == "unused"

    assert runner.run("from coverage import Coverage; Coverage.current() is None")


@pytest.mark.no_cover
def test_coverage_opt_out(selenium_standalone, wasm_coverage):
    with wasm_coverage(targets.pyodide(selenium_standalone)) as runner:
        assert decide(runner, True) == "taken"


def test_rejects_uninitialized_runner(wasm_coverage):
    with pytest.raises(TypeError, match="initialized pytest-pyodide runner"):
        with wasm_coverage(targets.pyodide(object())):
            pytest.fail("an invalid runner must fail before the test starts")


def test_rejects_invalid_snapshot(selenium_standalone_noload, wasm_coverage):
    selenium_standalone_noload.load_pyodide()
    selenium_standalone_noload.initialize_pyodide()

    class MissingSnapshot:
        discard_result = False

        def load_package(self, packages):
            selenium_standalone_noload.load_package(packages)

        def run(self, code):
            value = selenium_standalone_noload.run(code)
            return None if self.discard_result else value

    wrapped = MissingSnapshot()
    with pytest.raises(TypeError, match="invalid coverage snapshot"):
        with wasm_coverage(targets.pyodide(wrapped)) as runner:
            assert decide(runner, True) == "taken"
            wrapped.discard_result = True
'''
    )

    result = pytester.runpytest_subprocess(
        *node_options, "--cov", "--cov-report=html", "-v"
    )
    result.assert_outcomes(passed=5)
    assert "No Python files" not in result.stdout.str()
    assert "Wasm coverage collected from 2 tests" in result.stdout.str()
    data = CoverageData(basename=str(pytester.path / ".coverage"))
    data.read()
    contexts = data.contexts_by_lineno(str(program))
    assert contexts[3] == ["test_guest.py::test_existing_scope[node]"]
    assert contexts[4] == ["test_guest.py::test_custom_scope[node]"]
    assert "decision.py" in (pytester.path / "htmlcov/index.html").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    "options", [[], ["--cov", "--no-cov"]], ids=["plain", "no-cov"]
)
def test_existing_pyodide_coverage_decorator_can_opt_out(
    pytester: pytest.Pytester, node_options: tuple[str, str], options: list[str]
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

    result = pytester.runpytest_subprocess(*node_options, *options, "-q")
    result.assert_outcomes(passed=1)
    (shard,) = pytester.path.glob(".coverage.emscripten.*")
    data = CoverageData(basename=str(shard))
    data.read()
    assert any(path.endswith("test_guest.py") for path in data.measured_files())
    assert not (pytester.path / ".coverage").exists()
    assert "Wasm coverage" not in result.stdout.str()
