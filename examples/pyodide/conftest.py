from collections.abc import Iterator

import pytest

from coverage_wasm import Pyodide, targets
from coverage_wasm.pytest_plugin import WasmCoverage


@pytest.fixture
def selenium_covered(
    selenium_module_scope: Pyodide, wasm_coverage: WasmCoverage
) -> Iterator[Pyodide]:
    with wasm_coverage(targets.pyodide(selenium_module_scope)) as runner:
        yield runner
