from collections.abc import Callable
from pathlib import Path
from shutil import copytree, ignore_patterns

import coverage
import pytest
from wasi_python import Grant, run

from coverage_wasm.pytest_plugin import WasmCoverage

SOURCE = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture(scope="session")
def guest_packages(tmp_path_factory: pytest.TempPathFactory) -> Path:
    packages = tmp_path_factory.mktemp("guest-packages")
    assert coverage.__file__ is not None
    copytree(
        Path(coverage.__file__).parent,
        packages / "coverage",
        ignore=ignore_patterns("__pycache__", "*.so", "*.pyd"),
    )
    return packages


@pytest.fixture
def quote(
    tmp_path: Path, guest_packages: Path, wasm_coverage: WasmCoverage
) -> Callable[[int], int]:
    def run_quote(subtotal_cents: int) -> int:
        result = run(
            [
                "-m",
                "coverage",
                "run",
                "--branch",
                "--data-file=/output/.coverage",
                f"--context={wasm_coverage.context}",
                "--include=/app/*.py",
                "/app/shipping.py",
                str(subtotal_cents),
            ],
            root=True,
            grants=[
                Grant(SOURCE, "/app"),
                Grant(guest_packages, "/packages"),
                Grant(tmp_path, "/output", writable=True),
            ],
            import_path=["/packages"],
            env={"COVERAGE_CORE": "sysmon"},
        )
        assert result.exit_code == 0, result.stderr.decode()
        wasm_coverage.add_file(tmp_path / ".coverage")
        return int(result.stdout)

    return run_quote
