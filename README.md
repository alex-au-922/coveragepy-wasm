# coverage-wasm

**Python line and branch coverage from Wasm and the host, in one pytest report.**

[![100% end-to-end coverage gate](https://github.com/alex-au-922/coverage-wasm/actions/workflows/coverage.yml/badge.svg?branch=codex%2Fpypi-rc1&event=push)](https://github.com/alex-au-922/coverage-wasm/actions/workflows/coverage.yml?query=branch%3Acodex%2Fpypi-rc1)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](#compatibility)
[![MIT license](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Measure Python running in [Pyodide](#pyodide), [Workerd](#workerd), or
[CPython on WASI](#cpython-on-wasi) while you run pytest.
[`coverage.py`][coverage-py] measures code inside the guest.
The plugin brings its coverage data back to pytest-cov, which combines it with
host coverage in a standard `coverage.py` report.

## Contents

- [Quick start](#quick-start)
- [Runtimes](#runtimes)
  - [Pyodide](#pyodide)
  - [Workerd](#workerd)
  - [CPython on WASI](#cpython-on-wasi)
- [Coverage configuration](#coverage-configuration)
- [Compatibility](#compatibility)
- [Custom launchers](#custom-launchers)
- [Development and releases](#development-and-releases)

## Quick start

### Install from PyPI

The first stable release is pending. Once it is available, install it in your
test project with uv.

```sh
uv add --dev coverage-wasm
```

With pip, run `python -m pip install coverage-wasm` in your test environment.
Installing the package also installs [`coverage.py`][coverage-py] for coverage
measurement and `pytest-cov` for pytest integration. The distribution is
`coverage-wasm` on PyPI and imported as `coverage_wasm`.

### Latest preview from GitHub

To try the current development version, use the preview branch. Your GitHub
account needs access to the private repository.

```sh
uv add --dev 'git+https://github.com/alex-au-922/coverage-wasm.git@codex/pypi-rc1'
```

If you already have the preview branch checked out, install it directly with
`uv add --dev /path/to/coverage-wasm`.

### Run with coverage

Choose a runtime below, then run pytest with your usual coverage options.

```sh
uv run pytest --cov --cov-report=html
```

Pytest loads the plugin automatically. The run shows `Wasm coverage enabled`
and reports how many tests contributed guest data. Open `htmlcov/index.html`
to see the merged report. Add `-v` to see which tests contributed.

## Runtimes

| Runtime | What to use in pytest |
| --- | --- |
| [Pyodide](#pyodide) | A supported pytest-pyodide fixture or `targets.pyodide(runner)` |
| [Workerd](#workerd) | `targets.wrangler(bundle)` with a prebuilt Python Worker |
| [CPython on WASI](#cpython-on-wasi) | `targets.wasi(argv, grants=grants)` for a script and filesystem grants |

Each target can be opened with `with wasm_coverage(target) as runtime:`.
The [runnable examples](examples/README.md) show the fixtures, test commands,
and expected branches in each HTML report.

### Pyodide

Install `pytest-pyodide` in your test environment. Use a supported
function-scoped fixture such as
[`selenium_standalone`](https://github.com/pyodide/pytest-pyodide#usage)
for automatic coverage. For a shared or custom runner, attach coverage
in a host-side fixture.

```python
from collections.abc import Iterator

import pytest

from coverage_wasm import Pyodide, targets
from coverage_wasm.pytest_plugin import WasmCoverage


@pytest.fixture
def selenium_covered(
    selenium_module_scope: Pyodide, wasm_coverage: WasmCoverage
) -> Iterator[Pyodide]:
    with wasm_coverage(targets.pyodide(selenium_module_scope)) as runner:
        yield runner
```

The context collects coverage before the runner shuts down.
The [Pyodide example](examples/pyodide/README.md) exercises opposite branches
from the host and guest and shows both branches in one report.

### Workerd

#### Bundle contract

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

#### Run with pytest

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

#### Testcontainers and custom launchers

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

### CPython on WASI

Install `wasi-python` in your test environment. Pass your script arguments
and filesystem grants to `targets.wasi()`. Opening the target runs the script
and yields the completed result. Place this test beside the `src/` directory
and use the [example `shipping.py`](examples/wasi/src/shipping.py).

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
[WASI fixture](examples/wasi/tests/conftest.py).

The WASI runner uses your grants to map source files back to the host.
An explicit `coverage.py` `[paths]` configuration takes precedence.
Use `coverage.py`'s `omit` setting if a nested grant exposes files outside the
source tree you're measuring.

## Coverage configuration

Use `coverage.py`'s `[paths]` to describe where the same files live. For a project
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
guest coverage, and `coverage.py` maps the measured paths back to `src` when it
combines the data. `branch = true` enables branch coverage for both collectors.

```sh
uv run pytest --cov=src --cov-report=html
```

Set `[tool.coverage.html] directory` to change the HTML output directory
and `[tool.coverage.report] fail_under` to set a coverage threshold.

Run plain pytest for tests only, or pass `--no-cov` when coverage is enabled
in `addopts`. Use `@pytest.mark.no_cover` to skip guest instrumentation for
one test. If you use pytest-xdist by default, pass `-n 0` for the Wasm run.

## Compatibility

Requires host CPython 3.11+ and pytest 8.4+.

## Custom launchers

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
`GuestCoverage` supplies the test `context` and `coverage.py`'s `branch`,
`source`, `include`, and `omit` settings. Use those settings before running
the application and call `guest.save(snapshot)` with the native `coverage.py`
file bytes before the runtime or its output disappears.

`launch` returns the launcher's result. A one-shot launcher can return a
completed result after saving coverage. A server launcher can return a
context manager that saves coverage during exit, before shutting down the
server.

`source_aliases` supplies fallback host-to-guest paths for computing source
filters. `coverage.py`'s `[paths]` takes precedence and controls how snapshots
are combined. A launcher may also translate its snapshot's filenames before
saving, as the WASI adapter does with filesystem grants.

## Development and releases

Install [mise](https://mise.jdx.dev/getting-started.html) and start Docker,
then run these commands from the repository root.

```sh
mise install
mise build
mise test
```

`mise test` runs the full Nox matrix. Run `mise test 3.11` to select one host
version. The [CI workflow](.github/workflows/coverage.yml) builds one wheel
and runs the five host versions as parallel jobs for pull requests and pushes
to development branches. The 3.14 job also checks 100% package line and branch
coverage and runs the example projects. Open `htmlcov/index.html` after a full
local run or download the `coverage-wasm-reports` artifact for the package and
example HTML reports.

### Release process

Protect `main` with a GitHub rule that requires a pull request, code-owner
approval, and successful `build` and `Wasm E2E (Python …)` checks from the
[coverage workflow](.github/workflows/coverage.yml).
[`CODEOWNERS`](.github/CODEOWNERS) assigns review to `@alex-au-922`.
Add a second eligible code owner to approve PRs authored by Alex.

Set the package version in `pyproject.toml`, run `uv lock`, and update the
examples' matching wheel references. When the version bump reaches protected
`main`, [`release.yml`](.github/workflows/release.yml) runs the full test
matrix against that commit. It then creates the matching tag and publishes
stable distributions using the wheel and source archive from that run.

| Release | Package version | Generated tag | Distribution |
| --- | --- | --- | --- |
| Candidate | `0.2.0rc1` | `v0.2.0-rc.1` | GitHub Actions artifacts |
| Final | `0.2.0` | `v0.2.0` | PyPI and GitHub Actions artifacts |

Existing tags keep their original commit. Merge a new package version to
start another release.

Before the first stable release, register a
[pending Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
on PyPI for project `coverage-wasm`, owner `alex-au-922`, repository
`coverage-wasm`, and workflow `release.yml`. Leave the environment field
empty for this workflow.

See the [changelog](CHANGELOG.md) and [MIT license](LICENSE).

[coverage-py]: https://github.com/coveragepy/coveragepy
