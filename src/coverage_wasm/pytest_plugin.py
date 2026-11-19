from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast
from uuid import uuid4
from warnings import warn

import pytest
from coverage import Coverage, CoverageData
from coverage.results import should_fail_under

from coverage_wasm import workerd
from coverage_wasm.pyodide import (
    is_pyodide_fixture,
    source_filters,
    start_pyodide_coverage,
)

_HTML = pytest.StashKey[Path]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.getgroup("coverage-wasm").addoption(
        "--no-wasm-coverage", action="store_true", help="Disable Wasm coverage"
    )


class _Run:
    def __init__(self, config: pytest.Config, staging: Path) -> None:
        self.config = config
        self.staging = staging
        self.enabled = not config.getoption("no_wasm_coverage")
        use_pytest_cov = config.getoption(
            "cov_source", None
        ) is not None and not config.getoption("no_cov", False)
        self.host = Coverage.current() if use_pytest_cov else None
        self.options = self.host if self.host is not None else Coverage()
        self.shards: list[Path] = []

    def check_runner(self) -> None:
        if hasattr(self.config, "workerinput"):
            raise pytest.UsageError("coverage-wasm requires serial pytest; use -n 0")

    def save(self, payload: bytes, *, pyodide_context: str | None = None) -> None:
        self.check_runner()
        if not payload.startswith(b"SQLite format 3\x00"):
            raise ValueError(
                "Wasm coverage expects a native Coverage.py .coverage file"
            )

        name = f".coverage.wasm.{uuid4().hex}"
        shard = self.staging / name
        shard.write_bytes(payload)
        data = CoverageData(basename=str(shard))
        data.read()
        files = data.measured_files()
        if pyodide_context is not None and not any(data.lines(file) for file in files):
            warn(
                pytest.PytestWarning(
                    f"coverage-wasm: {pyodide_context}: No Python files measured "
                    "in Pyodide. Check Coverage.py source filters and [paths]."
                ),
                stacklevel=2,
            )
        if not files:
            shard.unlink()
            if pyodide_context is not None:
                return
            raise RuntimeError("The Wasm coverage snapshot has no measured files")

        if self.host is None:
            self.shards.append(shard)
            return
        if data.has_arcs() != self.host.get_option("run:branch"):
            raise ValueError(
                "Wasm and pytest-cov must use the same branch coverage mode"
            )
        base = self.config.invocation_params.dir / cast(
            str, self.host.get_option("run:data_file")
        )
        base.with_name(base.name + name.removeprefix(".coverage")).write_bytes(payload)

    def report(self) -> None:
        if not self.shards:
            return

        root = self.config.invocation_params.dir
        base = root / cast(str, self.options.get_option("run:data_file"))
        output = base.with_name(base.name + "-wasm")
        report = Coverage(data_file=output)
        report.combine([str(shard) for shard in self.shards], strict=True, keep=True)
        report.save()
        directory = root / cast(str, report.get_option("html:directory"))
        total = report.html_report(directory=str(directory))
        self.config.stash[_HTML] = directory / "index.html"
        minimum = cast(float, report.get_option("report:fail_under"))
        precision = cast(int, report.get_option("report:precision"))
        if should_fail_under(total, minimum, precision):
            pytest.fail(
                f"Wasm coverage {total:.{precision}f}% is below {minimum:g}%",
                pytrace=False,
            )


@pytest.fixture(scope="session")
def _wasm_coverage_run(
    pytestconfig: pytest.Config, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[_Run]:
    run = _Run(pytestconfig, tmp_path_factory.mktemp("coverage-wasm"))
    yield run
    run.report()


class WasmCoverage:
    """Collect native coverage from a guest owned by the current test fixture."""

    def __init__(self, run: _Run, context: str) -> None:
        self._run = run
        self.context = context

    def add_file(self, path: Path) -> None:
        """Collect a .coverage file from a runtime with a host-visible directory."""
        if self._run.enabled:
            self._run.save(path.read_bytes())

    def install_workerd(self, python_modules: Path, *, include: list[str]) -> None:
        """Stage a test bundle before its Worker starts."""
        if self._run.enabled:
            self._run.check_runner()
            workerd.install(
                python_modules,
                include=include,
                context=self.context,
                branch=cast(bool, self._run.options.get_option("run:branch")),
            )

    @contextmanager
    def workerd(
        self,
        execute: Callable[[list[str]], tuple[int | None, bytes]],
        *,
        port: int = 9229,
    ) -> Generator[None, None, None]:
        """Collect once, while the fixture still owns its running Worker."""
        if self._run.enabled:
            self._run.check_runner()
        try:
            yield
        finally:
            if self._run.enabled:
                status, payload = execute(workerd.snapshot_command(port))
                if status != 0:
                    raise RuntimeError(payload.decode(errors="replace"))
                self._run.save(payload)


@pytest.fixture
def wasm_coverage(
    request: pytest.FixtureRequest, _wasm_coverage_run: _Run
) -> WasmCoverage:
    return WasmCoverage(_wasm_coverage_run, request.node.nodeid)


@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(
    fixturedef: pytest.FixtureDef[object], request: pytest.FixtureRequest
) -> Generator[None, object, object]:
    runner = yield
    if request.config.getoption("no_wasm_coverage") or not is_pyodide_fixture(
        fixturedef.argname, fixturedef.func.__module__, fixturedef.scope
    ):
        return runner

    run = cast(_Run, request.getfixturevalue("_wasm_coverage_run"))
    run.check_runner()
    context = request.node.nodeid
    sources, mapped = source_filters(
        cast(list[str] | None, run.options.get_option("run:source")) or [],
        cast(dict[str, list[str]], run.options.get_option("paths")),
        request.config.invocation_params.dir,
    )
    finish = start_pyodide_coverage(
        runner,
        context=context,
        source=sources,
        branch=cast(bool, run.options.get_option("run:branch")),
        include=mapped or cast(list[str] | None, run.options.get_option("run:include")),
        omit=cast(list[str] | None, run.options.get_option("run:omit")),
    )
    request.addfinalizer(lambda: run.save(finish(), pyodide_context=context))
    return runner


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    report = config.stash.get(_HTML, None)
    if report is not None:
        terminalreporter.write_line(f"Wasm coverage HTML: {report}")
