# CPython on WASI

Run the shipping rule in WASI CPython with `wasi-python` 0.1.5. The tests check
the fee just below and at the free-shipping threshold. Run these commands from
the package root with uv and Python 3.11 or newer. The example installs its
WASI runtime and the local `coverage-wasm` wheel.

```sh
uv build --wheel
cd examples/wasi
uv run pytest --cov --cov-report=html
```

Open `output/htmlcov/index.html`. Both shipping branches are covered. The
report uses the fixture's grant to map guest `/app/shipping.py` to
`src/shipping.py` and shows the pytest case for each branch.

The [fixture](tests/conftest.py) opens a `targets.wasi()` target with
`wasm_coverage(target)`. It decides which application
files the guest may see. With `--cov`, the plugin stages Coverage.py, adds a
temporary output grant, and collects the guest's `.coverage` file. The
[test](tests/test_quote_wasi.py) checks the shipping amounts.

To run the same cases with the normal WASI runner, use `uv run pytest`.
