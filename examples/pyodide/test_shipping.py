from pytest_pyodide import copy_files_to_pyodide, run_in_pyodide  # pyright: ignore[reportMissingTypeStubs, reportUnknownVariableType]
from shipping import shipping_fee

from coverage_wasm import Pyodide


@copy_files_to_pyodide([("shipping.py", "/home/pyodide/shipping.py")])
@run_in_pyodide
def test_shipping_is_free_at_threshold(selenium_covered: Pyodide | None) -> None:
    from shipping import shipping_fee

    assert shipping_fee(100) == 0


def test_shipping_is_charged_below_threshold() -> None:
    assert shipping_fee(99) == 15
