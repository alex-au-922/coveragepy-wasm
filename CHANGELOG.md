# Changelog

## 0.2.0

- Use `pytest --cov` for both host and guest coverage. Report the tests that
  contribute guest data.
- Collect Python coverage from pytest-pyodide fixtures and from local Workerd
  and WASI runtimes that a test fixture owns.
- Collect coverage with one call in an existing Testcontainers Worker fixture.
- Run WASI scripts with coverage and reuse filesystem grants for source mapping.
- Open typed Workerd, WASI, and Pyodide targets with `wasm_coverage(target)`.
- Launch a prepared Python Worker with `targets.wrangler(bundle)` on macOS
  or Linux.
- Adapt another launcher with `wasm_coverage.launch(start)` and submit its
  Coverage.py snapshot through `GuestCoverage.save()`.
- Combine guest data into pytest-cov's Coverage.py collector so both appear
  in the same report.
- Apply Coverage.py path aliases to Pyodide source directories and warn when
  a fixture produces no executed Python lines.
- Require pytest 8.4 or newer and include the three consumer examples in
  the source distribution.
