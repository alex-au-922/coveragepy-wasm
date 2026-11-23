# Pyodide and native Python

Two tests exercise one shipping rule. Pyodide gets free shipping at the
threshold, and native Python pays the fee below it. Run both tests with uv,
Node.js 26, and npm. Start at the package root.

```sh
uv build --wheel
cd examples/pyodide
npm install --prefix .pyodide --no-save --no-package-lock pyodide@314.0.8
uv run --upgrade-package coverage-wasm pytest --cov --cov-report=html -k free_at_threshold
```

Open `htmlcov/index.html` and select `shipping.py`. The free-shipping branch
is covered and the paid branch is missing. This run selects the Pyodide test.

Run both tests to include the native Python branch in the same report.

```sh
uv run pytest --cov --cov-report=html:htmlcov-merged
```

Open `htmlcov-merged/index.html`. Both branches appear as covered in one
`shipping.py` entry.

The [guest test](test_shipping.py) requests
[`selenium_standalone`](https://github.com/pyodide/pytest-pyodide#usage)
from `pytest-pyodide`. With `--cov`, coverage starts automatically.
`@run_in_pyodide` runs the test in the guest and passes `None` as the runner
argument there. If your app is already installed in Pyodide, import it inside
the test.

The [coverage configuration](pyproject.toml) maps guest `/home/pyodide` to
this directory and enables branch coverage for both collectors.
