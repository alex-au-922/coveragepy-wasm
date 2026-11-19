# End-to-end examples

Each example is a small pytest project that installs the local wheel and runs
Python in a real WebAssembly runtime. Its README shows how to run the tests
and which branches to look for in the HTML report.

| Example | Tested runtime | Coverage handoff |
| --- | --- | --- |
| [Pyodide](pyodide/README.md) | Pyodide 314.0.8, pytest-pyodide 0.59.4, Node 22 | Pytest starts and stops coverage through the existing Pyodide fixture. |
| [Workerd](workerd/README.md) | Wrangler 4.164.0, Node 24.18.0, Python 3.14 | The fixture stages coverage in the test bundle and takes a snapshot before stopping the Worker. |
| [WASI](wasi/README.md) | CPython on Wasmtime via wasi-python 0.1.5 | The fixture passes the guest's native `.coverage` file to pytest. |

The [Pyodide example](pyodide/README.md) also shows how two tests can cover
opposite branches of one file, one from Pyodide and one from the host. Compare
its guest report with the combined pytest-cov report.

After rebuilding a local wheel under the same version, run
`uv lock --upgrade-package coverage-wasm` in an existing example to refresh
the wheel hash before running pytest again.
