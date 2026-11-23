from collections.abc import Callable
from pathlib import Path

import pytest
from wasi_python import Grant

from coverage_wasm import targets
from coverage_wasm.pytest_plugin import WasmCoverage

SOURCE = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture
def quote(wasm_coverage: WasmCoverage) -> Callable[[int], int]:
    def run_quote(subtotal_cents: int) -> int:
        target = targets.wasi(
            ["/app/shipping.py", str(subtotal_cents)],
            grants=[Grant(SOURCE, "/app")],
        )
        with wasm_coverage(target) as result:
            assert result.exit_code == 0, result.stderr.decode()
            return int(result.stdout)

    return run_quote
