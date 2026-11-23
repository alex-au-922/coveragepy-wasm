# Local Python Worker

Test a real local Python Worker over HTTP. The tests call `/hello` and an
unknown route, exercising both branches of the entrypoint. Use Node.js 26,
npm, uv, and Python 3.14 on macOS or Linux. Run these commands from the
package root.

```sh
uv build --wheel
cd examples/workerd
uv run --upgrade-package coverage-wasm pytest --cov --cov-report=html
```

Open `htmlcov/index.html`. The report shows both response branches in
`src/entrypoint.py`, each under its own pytest context.

The example's [session fixture](conftest.py) runs `npm ci` and
`pywrangler deploy --dry-run` in a temporary checkout. It supplies a bundle
directory with its config, entrypoint, and vendored modules. Each test uses
`targets.wrangler(bundle)` to start a fresh Worker and checks its response
over HTTP. When `--cov` is set, `pytest` collects guest coverage before stopping
the Worker. The package's [bundle contract](../../README.md#bundle-contract)
also works with an artifact from your own build pipeline.
