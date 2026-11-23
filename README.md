# coverage-wasm

![coverage-wasm logo](https://raw.githubusercontent.com/alex-au-922/coveragepy-wasm/main/docs/assets/coverage-wasm-wordmark.svg)

**A [`coverage.py`][coverage-py] addon for Python line and branch coverage
from Wasm and the host in one `pytest` report.**

[![Package coverage 100%](https://img.shields.io/badge/package%20coverage-100%25-brightgreen)](https://github.com/alex-au-922/coveragepy-wasm/actions/workflows/coverage.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](#compatibility)
[![MIT license](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[Documentation](https://alex-au-922.github.io/coveragepy-wasm/) · [Runnable examples](examples/README.md)

Measure Python running in Pyodide, Workerd, or CPython on WASI while you
run `pytest`.
[`coverage.py`][coverage-py] measures code inside the guest.
The plugin brings its coverage data back to `pytest-cov`, which combines it with
host coverage in a standard `coverage.py` report.

## Contents

- [Quick start](#quick-start)
- [Runtimes](#runtimes)
- [Coverage configuration](#coverage-configuration)
- [Compatibility](#compatibility)
- [Custom launchers](#custom-launchers)
- [Development and releases](#development-and-releases)

## Quick start

### Install from PyPI

For a published stable release, use uv in your test project.

```sh
uv add --dev coverage-wasm
```

With pip, run `python -m pip install coverage-wasm` in your test environment.
Installing the package also installs [`coverage.py`][coverage-py] for coverage
measurement and `pytest-cov` for `pytest` integration. The distribution is
`coverage-wasm` on PyPI and imported as `coverage_wasm`.

### Install from GitHub

Install from `main` for the latest development version.

```sh
uv add --dev git+https://github.com/alex-au-922/coveragepy-wasm.git --branch main
```

Run `uv lock --upgrade-package coverage-wasm` to update a locked `main` install.

For a fixed version, pick an existing [Git tag] and pass it to `--tag`.

```sh
uv add --dev git+https://github.com/alex-au-922/coveragepy-wasm.git --tag v0.2.0-rc.1
```

Install from a local checkout with `uv add --dev /path/to/coverage-wasm`.

### Run with coverage

Choose a runtime below, then run `pytest` with your usual coverage options.

```sh
uv run pytest --cov --cov-report=html
```

`pytest` loads the plugin automatically. The run shows `Wasm coverage enabled`
and reports how many tests contributed guest data. Open `htmlcov/index.html`
to see the merged report. Add `-v` to see which tests contributed.

## Runtimes

| Runtime | pytest integration |
| --- | --- |
| [Pyodide](https://alex-au-922.github.io/coveragepy-wasm/pyodide/) | `selenium_standalone` from `pytest-pyodide` |
| [Workerd](https://alex-au-922.github.io/coveragepy-wasm/workerd/) | `targets.wrangler(bundle)` with a prebuilt Python Worker |
| [CPython on WASI](https://alex-au-922.github.io/coveragepy-wasm/wasi/) | `targets.wasi(argv, grants=grants)` for a script and filesystem grants |

The [runnable examples](examples/README.md) include fixtures and show what to
expect in the HTML reports.

## Coverage configuration

Use `coverage.py`'s `[paths]` to map guest filenames back to your source tree.
Set `branch = true` to measure branch coverage. See the
[coverage configuration guide](https://alex-au-922.github.io/coveragepy-wasm/configuration/) for an example and
the report options.

## Compatibility

Requires host CPython 3.11+ and `pytest` 8.4+.

For branch coverage with the
[`sysmon` measurement core](https://coverage.readthedocs.io/en/7.17.3/config.html#run-core),
the Python process being measured needs Python 3.14 or newer.
On host Python 3.11–3.13, `coverage.py` can measure branches with `ctrace`.
For local Python Workers, the branch coverage requirement applies to
the Python version inside Workerd.

## Custom launchers

Implement `WasmCoverageTarget[T]` to integrate another runtime. See the
[custom launcher guide](https://alex-au-922.github.io/coveragepy-wasm/custom-launchers/) for the snapshot contract.

## Development and releases

Install [mise](https://mise.jdx.dev/getting-started.html) and start Docker,
then run these commands from the repository root.

```sh
mise install
mise build
mise test
```

`mise test` runs the full Nox matrix. Run `mise test 3.11` to select one host
version. Develop on a feature branch and open a pull request into `main`.
The [CI workflow](.github/workflows/coverage.yml) runs on feature branch pushes
and pull requests. It installs the built wheel on host Python 3.11–3.15 and runs
the package suite, including tests in Pyodide, Workerd, and WASI. The combined
report requires 100% package line and branch coverage across the full suite.
The 3.14 job also runs the examples and uploads their application coverage
reports separately.
After a full local run, open `htmlcov/index.html`. On GitHub, download the
`coverage-wasm-reports` and `coverage-wasm-example-reports` Actions artifacts.

Run `mise docs:build` to build and validate the documentation with Zensical.
GitHub Actions builds it on pull requests and deploys it to GitHub Pages from
`main`.

### Releases

The [release workflow](.github/workflows/release.yml) runs when a package
version changes on protected `main` or when triggered for an exact version on
`main`. It tests the commit and tags it. To check out tagged source in a
clone, use `git switch --detach v0.2.0`.

| Release | Example Git tag | Distribution |
| --- | --- | --- |
| Candidate | `v0.2.0-rc.1` | GitHub Actions artifacts |
| Stable | `v0.2.0` | PyPI and GitHub Actions artifacts |

See the [changelog](CHANGELOG.md) and [MIT license](LICENSE).

[coverage-py]: https://github.com/coveragepy/coveragepy
[Git tag]: https://github.com/alex-au-922/coveragepy-wasm/tags
