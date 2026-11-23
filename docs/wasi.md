# CPython on WASI

Install `wasi-python` in your test environment. Pass your script arguments
and filesystem grants to `targets.wasi()`. Opening the target runs the script
and yields the completed result. Place this test beside the `src/` directory
and use the [example `shipping.py`](https://github.com/alex-au-922/coveragepy-wasm/blob/main/examples/wasi/src/shipping.py).

```python
from pathlib import Path

from wasi_python import Grant

from coverage_wasm import targets
from coverage_wasm.pytest_plugin import WasmCoverage


def test_free_shipping(wasm_coverage: WasmCoverage) -> None:
    source = Path(__file__).resolve().parent / "src"
    target = targets.wasi(
        ["/app/shipping.py", "5000"], grants=[Grant(source, "/app")]
    )
    with wasm_coverage(target) as result:
        assert result.exit_code == 0, result.stderr.decode()
        assert result.stdout.strip() == b"0"
```

Python on WASI needs `sqlite3` for `coverage.py`. For other guest launchers,
pass a native coverage file to `wasm_coverage.add_file(path)`. See the
[WASI fixture](https://github.com/alex-au-922/coveragepy-wasm/blob/main/examples/wasi/tests/conftest.py).

The WASI runner uses your grants to map source files back to the host.
An explicit `coverage.py` `[paths]` configuration takes precedence.
Use `coverage.py`'s `omit` setting if a nested grant exposes files outside the
source tree you're measuring.
