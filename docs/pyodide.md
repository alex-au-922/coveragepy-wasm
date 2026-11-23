# Pyodide

With Node and npm available, install the test plugin and its Pyodide runtime.

```sh
uv add --dev pytest-pyodide==0.59.4
npm install --prefix .pyodide --no-save --no-package-lock pyodide@314.0.8
```

Set the runtime and guest source path in `pyproject.toml`.

```toml
[tool.pytest.ini_options]
addopts = "--runtime=node --dist-dir=.pyodide/node_modules/pyodide"
asyncio_default_fixture_loop_scope = "function"

[tool.coverage.run]
branch = true
include = ["*/shipping.py"]

[tool.coverage.paths]
shipping = [".", "/home/pyodide"]
```

Use the [`selenium_standalone`][pytest-pyodide-usage] fixture. With `--cov`, the
plugin collects guest coverage automatically. This test copies `shipping.py`
into Pyodide and runs the assertion there.

```python
from pytest_pyodide import copy_files_to_pyodide, run_in_pyodide

from coverage_wasm import Pyodide


@copy_files_to_pyodide([("shipping.py", "/home/pyodide/shipping.py")])
@run_in_pyodide
def test_shipping_is_free_at_threshold(selenium_standalone: Pyodide | None) -> None:
    from shipping import shipping_fee

    assert shipping_fee(100) == 0
```

Run `uv run pytest --cov --cov-report=html` and open `htmlcov/index.html`. The
[example `shipping.py`][shipping-rule] implements the rule used in the test.

The [Pyodide example][pyodide-example] exercises opposite branches from the host
and guest in one report. For a shared or custom runner, open
`wasm_coverage(targets.pyodide(runner))` in the fixture that owns the runner.

[pytest-pyodide-usage]: https://github.com/pyodide/pytest-pyodide#usage
[shipping-rule]: https://github.com/alex-au-922/coveragepy-wasm/blob/main/examples/pyodide/shipping.py
[pyodide-example]: https://github.com/alex-au-922/coveragepy-wasm/tree/main/examples/pyodide
