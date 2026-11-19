# coverage-wasm

Collect Python line and branch coverage from WebAssembly in pytest.
Measure Pyodide, local Python Workers, or CPython on WASI and read the results
in a standard Coverage.py report. With `pytest-cov`, you can see host and guest
execution in one report.

## Install and run

Use Python 3.11 or newer and pytest 8.4 or newer on the host. The preview
installs Coverage.py 7.17.3 as a dependency. Build the wheel from the source
tree.

```sh
uv build --wheel
```

From your test project, install the local wheel and run pytest as usual.

```sh
uv add --dev /path/to/coverage-wasm/dist/coverage_wasm-0.2.0-py3-none-any.whl
uv run pytest
```

Pytest loads the plugin automatically. It starts coverage for supported
function-scoped `pytest-pyodide` fixtures such as `selenium_standalone`.
For Workerd or WASI, add the runtime handoff below to the fixture that owns
your guest. Keep your test assertions about the application.

In a standalone run, pytest prints the HTML report path, `htmlcov/index.html`
by default. The combined guest data goes in `.coverage-wasm`, or the
configured Coverage.py data filename with `-wasm` appended. Use Coverage.py's
`[html] directory` and `[report] fail_under` settings to change the report
path and coverage gate. See the [runnable examples](examples/README.md) for
tested runtime versions, setup commands, and expected branch results.

## Map guest and host source paths

Use Coverage.py's `[paths]` to describe where the same files live. For a project
with local `src/shipping.py` and guest `/app/shipping.py`, use this configuration
in `pyproject.toml`.

```toml
[tool.coverage.run]
branch = true
source = ["src"]

[tool.coverage.paths]
application = ["src", "/app"]

[tool.coverage.html]
show_contexts = true
```

Put the host directory first. The plugin applies the guest alias when starting
Pyodide coverage, and Coverage.py maps the measured paths back to `src` when it
combines the data. If a Pyodide case reports zero measured files, check that it
runs the application in the guest and that the configured paths match.

Mapped directories select files by path inside Pyodide. A standalone guest
report can omit files that the guest never imported. When host coverage is
enabled, Coverage.py also uses the configured host source tree when it
calculates the combined total.

To combine host and guest coverage, use the existing pytest-cov command. Both
collectors must use the same measurement mode. Here `branch = true` configures
branch coverage for both, and pytest-cov writes the combined data and HTML.

```sh
uv run pytest --cov=src --cov-report=html
```

## Workerd

Stage coverage in a copy of the Python Worker test bundle before starting
Wrangler. Enable its inspector on loopback. While the Worker is still running,
wrap the fixture's yield with `wasm_coverage.workerd` so it saves a snapshot
before shutdown.

```python
wasm_coverage.install_workerd(
    bundle / "python_modules", include=["*/entrypoint.py"]
)

# Start Wrangler and wait for it to be ready.
with wasm_coverage.workerd(execute_inspector, port=inspector_port):
    yield worker_url
```

`execute_inspector` runs the supplied command in an environment that can reach
the loopback inspector and resolve Node's `ws` module. It returns
`(exit_code, output_bytes)`. Use one snapshot per Worker and a fresh test copy
per pytest context. Workerd branch coverage uses Python 3.14 or newer and the
`sysmon` core. See the [Workerd fixture](examples/workerd/conftest.py).

## CPython on WASI

Run Coverage.py inside the guest and write its native `.coverage` file to a
writable directory mounted from the host. Before releasing that directory,
hand the file to the pytest fixture.

```python
wasm_coverage.add_file(output_directory / ".coverage")
```

Set the guest's coverage context to `wasm_coverage.context` to label the
recorded lines with the pytest case. Python on WASI needs `sqlite3` for
Coverage.py. See the [WASI fixture](examples/wasi/tests/conftest.py).

If you own the guest collector, `coverage_wasm.snapshot(collector)` saves its
data and returns the native file as bytes.

## Existing Pyodide suites

Use one collector per case. To migrate tests from
`@run_in_pyodide_coverage`, use `@run_in_pyodide` with a supported
`pytest-pyodide` fixture. Move any `coverage_args` filters into your
Coverage.py configuration. To keep the upstream coverage decorator,
run pytest with `--no-wasm-coverage`.

Run Wasm coverage serially. If your project uses pytest-xdist by default,
use `pytest -n 0` for the Wasm run.

See the [changelog](CHANGELOG.md) for preview changes.
