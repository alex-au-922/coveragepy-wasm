# Workerd

[Cloudflare's `workerd`][cloudflare-workerd] runs Python Workers locally through
Wrangler.

## Bundle contract

Build the Python Worker with your project's usual build process and give
coverage-wasm the resulting directory. It must be runnable with local
Wrangler and `--no-bundle`. Include the Wrangler config, the built Python
entrypoint and modules, and any runtime files referenced by the config.
Keep paths relative and put vendored `python_modules/` next to the config.
For example, a config with `main = "src/entrypoint.py"` can use this layout.

```text
worker-bundle/
├── wrangler.toml
├── src/
│   └── entrypoint.py
└── python_modules/
```

`targets.wrangler(bundle)` looks for `wrangler.toml` at the bundle root.
Pass `config=Path("deployments/cloudflare-d1/wrangler.toml")` for a nested
config, or `config=Path("wrangler.jsonc")` for that filename. The path is
relative to the bundle. Use Node 26 on macOS or Linux. Put Wrangler on
`PATH` or pass the path to a project-installed Wrangler with `executable`.

Check that Wrangler can serve the prepared directory before wiring it into
`pytest`.

```sh
wrangler dev --local --no-bundle --config ./artifacts/worker/wrangler.toml
```

## Run with pytest

Supply `worker_bundle` from your project's build fixture or point it at
an artifact already produced by your CI build. The coverage fixture only
needs the resulting `Path`.

```python
from collections.abc import Iterator
from pathlib import Path

import pytest
from coverage_wasm import targets
from coverage_wasm.pytest_plugin import WasmCoverage


@pytest.fixture(scope="session")
def worker_bundle() -> Path:
    return Path(__file__).resolve().parent / "artifacts/worker"


@pytest.fixture
def worker_url(
    worker_bundle: Path, wasm_coverage: WasmCoverage
) -> Iterator[str]:
    with wasm_coverage(targets.wrangler(worker_bundle)) as worker:
        yield worker.url
```

The target starts a fresh local Worker for each test and stops it when the
fixture exits. With `--cov`, it instruments a temporary copy of the bundle
and collects coverage before shutdown. For a project with host sources in
`src/`, map Workerd's `/session/metadata` paths back to those sources.

```toml
[tool.coverage.run]
branch = true
source = ["src"]
omit = ["*/python_modules/**"]

[tool.coverage.paths]
source = ["src", "/session/metadata"]
```

```sh
uv run pytest --cov --cov-report=html
```

Open `htmlcov/index.html`. Workerd branch coverage uses guest Python 3.14
and the `sysmon` core. The [Workerd example](https://github.com/alex-au-922/coveragepy-wasm/blob/main/examples/workerd/README.md)
shows a project that builds its own bundle with Pywrangler.

## Testcontainers and custom launchers

Pass the configured Testcontainers Worker and its build artifact to
`targets.workerd_container()`.

```python
from coverage_wasm import targets

with wasm_coverage(targets.workerd_container(worker, worker_bundle)) as running:
    yield running
```

The context manager copies the bundle into the container before startup and
uses a test copy with the collector under `--cov`. By default the bundle is
copied under `/` with its original directory name. Set `python_modules` to a
relative path if the bundle stores its dependencies in a deployment
subdirectory. It uses Node 26 and Wrangler's loopback inspector on port 9229 to
collect before shutdown. Use a fresh Worker per test to preserve its coverage
context.

For a custom launcher, pass it along with the build artifact. The launcher
is a context manager factory that accepts the path to serve and yields a
running Worker with `inspector_port` and
`execute(argv)` for the snapshot command. The target supplies the test copy
and collects coverage before the launcher exits.

```python
target = targets.workerd(worker_bundle, start=local_worker)
with wasm_coverage(target) as worker:
    yield worker.url
```

[cloudflare-workerd]: https://github.com/cloudflare/workerd
