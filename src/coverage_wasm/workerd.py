from base64 import b64encode
from importlib import import_module
from pathlib import Path
from shutil import copytree, ignore_patterns

import coverage

from coverage_wasm import snapshot


def install(
    python_modules: Path, *, include: list[str], context: str = "", branch: bool = True
) -> None:
    """Install coverage into an already built, test-only Python Worker bundle."""
    ignore = ignore_patterns("__pycache__", "*.so", "*.pyd")
    copytree(Path(coverage.__file__).parent, python_modules / "coverage", ignore=ignore)
    copytree(Path(__file__).parent, python_modules / "coverage_wasm", ignore=ignore)
    (python_modules / "coverage_wasm.pth").write_text(
        "import coverage_wasm.workerd; "
        f"coverage_wasm.workerd.start({include!r}, {context!r}, {branch!r})\n",
        encoding="utf-8",
    )


def start(include: list[str], context: str, branch: bool = True) -> None:
    """Start the collector when Workerd processes the test bundle's .pth file."""
    collector = coverage.Coverage(
        data_file="/tmp/wasm-coverage",
        config_file=False,
        branch=branch,
        include=include,
        context=context,
    )
    collector.set_option("run:core", "sysmon")
    collector.start()
    if dict(collector.sys_info())["core"] != "SysMonitor":
        raise RuntimeError("Workerd branch coverage requires the sysmon core")

    def export() -> str:
        return b64encode(snapshot(collector)).decode("ascii")

    ffi = import_module("pyodide.ffi")
    import_module("js").globalThis.wasmCoverage = ffi.create_once_callable(export)


def snapshot_command(port: int = 9229) -> list[str]:
    """Return a Node command that writes a local Workerd snapshot to stdout."""
    script = (
        Path(__file__).with_name("workerd_snapshot.mjs").read_text(encoding="utf-8")
    )
    return ["node", "--input-type=module", "-e", script, str(port)]
