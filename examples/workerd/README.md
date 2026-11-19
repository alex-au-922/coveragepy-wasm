# Local Python Worker

Test a real local Python Worker over HTTP. The tests call `/hello` and an
unknown route, exercising both branches of the entrypoint. Use Node 24,
Python 3.14, and uv on macOS or Linux. Run these commands from the package root.

```sh
uv build --wheel
cd examples/workerd
npm install
uv run pytest -q
```

Open `htmlcov/index.html`. The report shows both response branches in
`src/entrypoint.py`, each under its own pytest context.

The [fixture](conftest.py) builds the bundle once, starts a local Wrangler
instance per test, and collects coverage through its loopback inspector before
shutdown. The [tests](test_worker.py) check the HTTP status and body.
