# Pyodide and native Python

Two tests exercise one shipping rule. Pyodide gets free shipping at the
threshold, and native Python pays the fee below it. Run both tests with uv,
Node.js 22, and npm. Start at the package root.

```sh
uv build --wheel
cd examples/pyodide
npm install --prefix .pyodide --no-save --no-package-lock pyodide@314.0.8
uv run pytest
```

Open `htmlcov/index.html` and select `shipping.py`. The free-shipping branch
is covered and the paid branch is missing. Both tests passed, and the report
contains just the measured Pyodide execution.

Use pytest-cov to add the native Python test to the report.

```sh
uv run pytest --cov --cov-report=html:htmlcov-merged
```

Open `htmlcov-merged/index.html`. Both branches now appear as covered in one
`shipping.py` entry. The [tests](test_shipping.py) use a regular Pyodide fixture
to run the application. The [coverage configuration](pyproject.toml) maps
guest `/app` to this directory and enables branch coverage for both collectors.
