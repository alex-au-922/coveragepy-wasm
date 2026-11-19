# Changelog

## 0.2.0 preview

- Collect Python coverage from pytest-pyodide fixtures and from local Workerd
  and WASI runtimes that a test fixture owns.
- Generate Coverage.py HTML automatically or include the guest data in an
  existing pytest-cov report.
- Apply Coverage.py path aliases to Pyodide source directories and warn when
  a fixture produces no executed Python lines.
- Require pytest 8.4 or newer and include the three consumer examples in
  the source distribution.
