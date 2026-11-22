# coverage-wasm

[![100% end-to-end coverage gate](https://github.com/alex-au-922/coverage-wasm/actions/workflows/ci.yml/badge.svg?branch=codex%2Fpypi-rc1&event=push)](https://github.com/alex-au-922/coverage-wasm/actions/workflows/ci.yml?query=branch%3Acodex%2Fpypi-rc1)

Collect Python line and branch coverage from WebAssembly in pytest.
Measure Pyodide, local Python Workers, or CPython on WASI alongside your host
tests in the same pytest-cov report.

`coverage-wasm` is an independent pytest plugin. Coverage.py measures Python
in the guest and writes its native coverage data. The plugin brings that data
back to pytest-cov, which combines it with host coverage and generates the
usual Coverage.py reports. Pytest loads the integration through its `pytest11`
entry point. The distribution is `coverage-wasm` and the Python import is
`coverage_wasm`.

## Install and run

Use Python 3.11 or newer and pytest 8.4 or newer on the host. The preview
installs Coverage.py 7.17.3 as a dependency. Install it from GitHub using an
account with access to the private repository.

```sh
uv add --dev git+https://github.com/alex-au-922/coverage-wasm
```

If you have a local checkout, add its source directory directly.

```sh
uv add --dev /path/to/coverage-wasm
```

After publication on PyPI, install a final release with
`uv add --dev coverage-wasm`. For a release candidate, download the wheel
from the tagged GitHub Actions run and install it with
`uv add --dev ./coverage_wasm-0.2.0rc1-py3-none-any.whl`.

Request the `wasm_coverage` pytest fixture and open a target with
`with wasm_coverage(target) as runtime:`. Each target yields its native
runner, container, or completed result. Existing supported
`pytest-pyodide` fixtures connect automatically.

| Runtime | Setup in the fixture that launches the guest |
| --- | --- |
| [Pyodide](#pyodide) | Use an existing supported fixture, or create a target with `targets.pyodide(runner)`. |
| [Workerd](#workerd) | Pass a prebuilt Python Worker directory to `targets.wrangler(bundle)`. |
| [CPython on WASI](#cpython-on-wasi) | Use `targets.wasi(argv, grants=grants)` with your script arguments and filesystem grants. |

```sh
uv run pytest --cov --cov-report=html
```

Pytest loads the plugin automatically. `--cov` enables host and guest coverage
in one report. Pytest announces Wasm coverage and reports how many tests
contributed guest data. Use `-v` to see their test IDs.

`--cov-report=html` writes `htmlcov/index.html` by default. The report path and
coverage threshold follow Coverage.py's `[html] directory` and
`[report] fail_under` settings. Run plain pytest for tests only, or use
`--no-cov` if coverage is configured in `addopts`. Use
`@pytest.mark.no_cover` to skip guest instrumentation for one test before its
fixtures run. The [runnable examples](examples/README.md) show each runtime's
setup and expected coverage results.

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
guest coverage, and Coverage.py maps the measured paths back to `src` when it
combines the data. If a Pyodide case reports zero measured files, check that
the guest runs the application and that the configured paths match. Here
`branch = true` enables branch coverage for both collectors.

```sh
uv run pytest --cov=src --cov-report=html
```

## Workerd

### Bundle contract

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
relative to the bundle. Use Node 24 on macOS or Linux. Put Wrangler on
`PATH` or pass the path to a project-installed Wrangler with `executable`.

Check that Wrangler can serve the prepared directory before wiring it into
pytest.

```sh
wrangler dev --local --no-bundle --config ./artifacts/worker/wrangler.toml
```

### Run with pytest

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
and the `sysmon` core. The [Workerd example](examples/workerd/README.md)
shows a project that builds its own bundle with Pywrangler.

### Testcontainers and custom launchers

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
subdirectory. It uses Node 24 and Wrangler's loopback inspector on port 9229 to
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

## CPython on WASI

Pass your existing script arguments and filesystem grants to `targets.wasi()`.
Opening the target runs the script and yields the completed result.

```python
target = targets.wasi(
    ["/app/shipping.py", "100"], grants=[Grant(source, "/app")]
)
with wasm_coverage(target) as result:
    assert result.exit_code == 0, result.stderr.decode()
```

Python on WASI needs `sqlite3` for Coverage.py. For other guest launchers,
pass a native coverage file to `wasm_coverage.add_file(path)`. See the
[WASI fixture](examples/wasi/tests/conftest.py).

The WASI runner uses your grants to map source files back to the host.
An explicit Coverage.py `[paths]` configuration takes precedence.
Use Coverage.py's `omit` setting if a nested grant exposes files outside the
source tree you're measuring.

## Pyodide

Use your existing supported function-scoped `pytest-pyodide` fixture for
automatic coverage. With an initialized runner of your own, attach
coverage in a host-side fixture or test.

```python
with wasm_coverage(targets.pyodide(runner)) as pyodide:
    assert pyodide.run("2 + 2") == 4
```

The context yields your runner and exports coverage on exit. A context
around an already-covered runner reuses its active per-test collector.
Your runner fixture still owns shutdown.

To migrate from `@run_in_pyodide_coverage`, use `@run_in_pyodide` with a
supported fixture and move any `coverage_args` filters into your Coverage.py
configuration. Suites using the upstream coverage decorator can run it with a
plain pytest invocation.

## Launcher contract

An integration can implement `WasmCoverageTarget[T]`, a callable that accepts
the coverage fixture and returns a context manager yielding `T`. Use
`wasm_coverage.launch(start)` inside that target to get guest coverage settings
and submit its snapshot.

```python
from collections.abc import Callable
from typing import TypeVar

from coverage_wasm import GuestCoverage

Result = TypeVar("Result")

def launch(
    self,
    start: Callable[[GuestCoverage | None], Result],
    *,
    source_aliases: dict[str, list[str]] | None = None,
) -> Result: ...
```

`start` receives `None` when coverage is disabled. With coverage enabled,
`GuestCoverage` supplies the test `context` and Coverage.py's `branch`,
`source`, `include`, and `omit` settings. Use those settings before running
the application and call `guest.save(snapshot)` with the native Coverage.py
file bytes before the runtime or its output disappears.

`launch` returns the launcher's result. A one-shot launcher can return a
completed result after saving coverage. A server launcher can return a
context manager that saves coverage during exit, before shutting down the
server.

`source_aliases` supplies fallback host-to-guest paths for computing source
filters. Coverage.py's `[paths]` takes precedence and controls how snapshots
are combined. A launcher may also translate its snapshot's filenames before
saving, as the WASI adapter does with filesystem grants.

Run Wasm coverage serially. If your project uses pytest-xdist by default,
use `pytest -n 0` for the Wasm run.

## Development and releases

Build the wheel and source distribution locally with `uv build --no-sources`.
Run the installed wheel through Nox on Python 3.11 through 3.15. The 3.11
session also checks the project's minimum pytest version, 8.4.

```sh
uvx nox==2026.10.20 --error-on-missing-interpreters -s tests -- dist/coverage_wasm-0.2.0rc1-py3-none-any.whl
```

The [CI workflow](.github/workflows/ci.yml) runs on pushes and pull requests.
It installs the built wheel and exercises it in Pyodide, WASI, and Workerd,
including Workerd over HTTP through Testcontainers. The coverage badge
follows the CI gate, which requires 100% Python line and branch coverage
of the package. The `coverage-wasm-reports` artifact contains the package
report at `htmlcov/index.html` and separate HTML reports for example apps.

For a release, set the Python package version in `pyproject.toml`, run
`uv lock`, and update the examples' matching wheel references. Git tags
use SemVer with a `v` prefix. Python artifacts use PEP 440 versions.

| Release | Git tag | Python version | Distribution |
| --- | --- | --- | --- |
| Candidate | `v0.2.0-rc.1` | `0.2.0rc1` | GitHub Actions artifacts |
| Final | `v0.2.0` | `0.2.0` | PyPI after a published GitHub Release |

Pushing either tag runs CI and saves the tested wheel and source distribution
as GitHub Actions artifacts. A GitHub prerelease can use the RC tag. The
[PyPI workflow](.github/workflows/release.yml) uploads distributions only
for a published final GitHub Release, after verifying its tag, package
version, and test results.

Before the first final release, register a [pending Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
on PyPI for project `coverage-wasm`, owner `alex-au-922`, repository
`coverage-wasm`, and workflow `release.yml`. Leave the environment field
empty for this workflow.

See the [changelog](CHANGELOG.md) and [MIT license](LICENSE).
