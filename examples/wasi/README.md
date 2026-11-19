# CPython on WASI

Run the shipping rule in WASI CPython with `wasi-python` 0.1.5. The tests check
the fee just below and at the free-shipping threshold. Run these commands from
the package root with uv and Python 3.11 or newer. The example installs its
WASI runtime and the local `coverage-wasm` wheel.

```sh
uv build --wheel
cd examples/wasi
uv run pytest
```

Open `output/htmlcov/index.html`. Both shipping branches are covered. The
report maps guest `/app/shipping.py` to `src/shipping.py` and shows the pytest
case for each branch.

The [fixture](tests/conftest.py) stages the pure-Python Coverage.py package,
grants the guest a writable output directory, and passes its `.coverage` file
to `wasm_coverage.add_file`. The [test](tests/test_quote_wasi.py) checks the
shipping amounts.
