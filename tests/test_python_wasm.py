import json
from importlib.metadata import version
from importlib.util import find_spec
from os import getenv
from pathlib import Path
from shutil import copyfile
from typing import Protocol

import pytest
from coverage import Coverage, __version__

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = "wasm::decision"
DECISION = """\
def decide(take_branch):
    if take_branch:
        return "taken"
    return "unused"

assert decide(True) == "taken"
"""
MEASURE = """\
import os
import sys
from pathlib import Path
from platform import machine
from runpy import run_path

assert sys.platform in {"emscripten", "wasi"}
assert machine() == "wasm32"
project = Path("/project")
sys.path[:0] = [str(wheel) for wheel in sorted(project.glob("*.whl"))]

import coverage
import coverage_wasm

assert ".whl/" in coverage.__file__
assert ".whl/" in coverage_wasm.__file__

source = str(project / "decision.py")
artifacts = project / "artifacts"
os.chdir(artifacts)
collector = coverage.Coverage(
    data_file=artifacts / "guest-coverage",
    config_file=False,
    branch=True,
    include=[source],
    context="wasm::decision",
)
collector.set_option("run:core", "sysmon")
with collector.collect():
    assert dict(collector.sys_info())["core"] == "SysMonitor"
    run_path(source)
    (artifacts / ".coverage.guest").write_bytes(coverage_wasm.snapshot(collector))
"""


class PyodideGuest(Protocol):
    def run_js(self, code: str) -> object: ...


@pytest.fixture
def guest_project(tmp_path: Path) -> Path:
    pure_wheel = getenv("WASM_COVERAGE_PURE_WHEEL")
    if pure_wheel is None:
        pytest.skip("Set WASM_COVERAGE_PURE_WHEEL to the pure Python Coverage.py wheel")

    coverage_wheel = Path(pure_wheel)
    assert coverage_wheel.name == f"coverage-{__version__}-py3-none-any.whl"
    package_version = version("coverage-wasm")
    package_wheel = ROOT / "dist" / f"coverage_wasm-{package_version}-py3-none-any.whl"
    assert package_wheel.is_file(), f"Build the {package_version} coverage-wasm wheel"
    for wheel in [coverage_wheel, package_wheel]:
        copyfile(wheel, tmp_path / wheel.name)

    (tmp_path / "decision.py").write_text(DECISION, encoding="utf-8")
    (tmp_path / "measure.py").write_text(MEASURE, encoding="utf-8")
    (tmp_path / "artifacts").mkdir()
    return tmp_path


def assert_native_report(project: Path) -> None:
    artifacts = project / "artifacts"
    shard = artifacts / ".coverage.guest"
    assert shard.read_bytes().startswith(b"SQLite format 3\x00")
    config = project / ".coveragerc"
    config.write_text(
        f"[paths]\nsource =\n    {project}\n    /project\n", encoding="utf-8"
    )
    report = Coverage(data_file=project / ".coverage", config_file=str(config))
    report.combine(data_paths=[str(artifacts)], strict=True, keep=True)
    report.save()
    assert report.get_data().measured_contexts() == {CONTEXT}

    json_path = project / "coverage.json"
    report.json_report(outfile=str(json_path))
    html_dir = project / "htmlcov"
    report.html_report(directory=str(html_dir), show_contexts=True)
    assert "decision.py" in (html_dir / "index.html").read_text(encoding="utf-8")
    files = json.loads(json_path.read_text(encoding="utf-8"))["files"]
    ((filename, entry),) = files.items()
    assert Path(filename).name == "decision.py"
    assert entry["executed_branches"] == [[2, 3]]
    assert entry["missing_branches"] == [[2, 4]]
    assert entry["executed_lines"] == [1, 2, 3, 6]
    assert entry["missing_lines"] == [4]


@pytest.mark.skipif(
    find_spec("pytest_pyodide") is None, reason="Requires pytest-pyodide"
)
def test_node_pyodide_snapshot(
    guest_project: Path, selenium_standalone: PyodideGuest
) -> None:
    files = {file.name: str(file) for file in guest_project.iterdir() if file.is_file()}
    output = str(guest_project / "artifacts" / ".coverage.guest")
    selenium_standalone.run_js(f"""
        const fs = require("node:fs");
        pyodide.FS.mkdir("/project");
        pyodide.FS.mkdir("/project/artifacts");
        for (const [name, path] of Object.entries({json.dumps(files)})) {{
            pyodide.FS.writeFile(`/project/${{name}}`, fs.readFileSync(path));
        }}
        pyodide.runPython(`
import sys
from runpy import run_path
assert sys.platform == "emscripten"
run_path("/project/measure.py")
`);
        fs.writeFileSync({json.dumps(output)}, pyodide.FS.readFile("/project/artifacts/.coverage.guest"));
    """)
    assert_native_report(guest_project)


def test_wasi_python_snapshot(guest_project: Path) -> None:
    wasi_python = pytest.importorskip("wasi_python")
    result = wasi_python.run(
        [
            "-c",
            'import sys; assert sys.platform == "wasi"; '
            'from runpy import run_path; run_path("/project/measure.py")',
        ],
        grants=[wasi_python.Grant(guest_project, "/project", writable=True)],
    )
    assert result.exit_code == 0, result.stderr.decode()
    assert_native_report(guest_project)
