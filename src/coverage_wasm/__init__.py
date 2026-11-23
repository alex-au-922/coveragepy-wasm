from pathlib import Path

from coverage import Coverage

from coverage_wasm._guest import GuestCoverage
from coverage_wasm.pyodide import PyodideRunner as Pyodide
from coverage_wasm.targets import WasmCoverageTarget

__all__ = ["GuestCoverage", "Pyodide", "WasmCoverageTarget", "snapshot"]


def snapshot(collector: Coverage) -> bytes:
    """Save the collector and return the native .coverage file."""
    collector.save()
    return Path(collector.get_data().data_filename()).read_bytes()
