# Pyodide and native Python

Two tests exercise one shipping rule. Pyodide gets free shipping at the
threshold, and native Python pays the fee below it. Run both tests with uv,
Node.js 22, and npm. Start at the package root.

```sh
uv build --wheel
cd examples/pyodide
npm install --prefix .pyodide --no-save --no-package-lock pyodide@314.0.8
uv run pytest --cov --cov-report=html -k free_at_threshold
```

Open `htmlcov/index.html` and select `shipping.py`. The free-shipping branch
is covered and the paid branch is missing. This run selects the Pyodide test.

Run both tests to include the native Python branch in the same report.

```sh
uv run pytest --cov --cov-report=html:htmlcov-merged
```

Open `htmlcov-merged/index.html`. Both branches appear as covered in one
`shipping.py` entry.

The [fixture](conftest.py) takes the initialized `selenium_module_scope`
runner from pytest-pyodide and attaches coverage for the current test.

```python
with wasm_coverage(targets.pyodide(selenium_module_scope)) as runner:
    yield runner
```

The [guest test](test_shipping.py) uses this fixture with
`@run_in_pyodide` and copies in the example's source file. The decorator
passes `None` for the runner argument inside the guest. If your app is
already installed in Pyodide, import it inside the test. Suites using a
supported fixture such as `selenium_standalone` can collect automatically.

The [coverage configuration](pyproject.toml) maps guest `/home/pyodide` to
this directory and enables branch coverage for both collectors.
