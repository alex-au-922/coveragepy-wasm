# Coverage configuration

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

Run `pytest` for tests only, or pass `--no-cov` when coverage is enabled
in `addopts`. Use `@pytest.mark.no_cover` to skip guest instrumentation for
one test. If you use `pytest-xdist` by default, pass `-n 0` for the Wasm run.

## Compatibility

Requires host CPython 3.11+ and `pytest` 8.4+.

For branch coverage with the
[`sysmon` measurement core](https://coverage.readthedocs.io/en/7.17.3/config.html#run-core),
the Python process being measured needs Python 3.14 or newer.
On host Python 3.11–3.13, `coverage.py` can measure branches with `ctrace`.
For local Python Workers, the branch coverage requirement applies to
the Python version inside Workerd.
