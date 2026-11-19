from pathlib import Path
from typing import Protocol

import pytest
from shipping import shipping_fee


class Pyodide(Protocol):
    def run(self, code: str) -> object: ...


@pytest.fixture
def shipping_in_pyodide(selenium_standalone: Pyodide) -> Pyodide:
    source = Path(__file__).with_name("shipping.py").read_text(encoding="utf-8")
    selenium_standalone.run(f"""
from pathlib import Path
from runpy import run_path

module = Path('/app/shipping.py')
module.parent.mkdir(exist_ok=True)
module.write_text({source!r}, encoding='utf-8')
shipping_fee = run_path(str(module))['shipping_fee']
""")
    return selenium_standalone


def test_shipping_is_free_at_threshold(shipping_in_pyodide: Pyodide) -> None:
    assert shipping_in_pyodide.run("shipping_fee(100)") == 0


def test_shipping_is_charged_below_threshold() -> None:
    assert shipping_fee(99) == 15
