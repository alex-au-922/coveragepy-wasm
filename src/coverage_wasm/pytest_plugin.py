from __future__ import annotations

from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from contextlib import AbstractContextManager, ExitStack, contextmanager
from os import PathLike
from pathlib import Path
from shutil import copytree
from tempfile import mkdtemp
from types import TracebackType
from typing import TYPE_CHECKING, Protocol, Self, TypeVar, cast
from uuid import uuid4
from warnings import warn

import pytest
from coverage import Coverage, CoverageData

from coverage_wasm import targets, wasi, workerd
from coverage_wasm._guest import GuestCoverage
from coverage_wasm.pyodide import (
    PyodideRunner,
    is_pyodide_fixture,
    source_filters,
    start_pyodide_coverage,
)
from coverage_wasm.targets import WasmCoverageTarget

if TYPE_CHECKING:
    from wasi_python import Completed, Grant


class WorkerdContainer(Protocol):
    def with_copy_into_container(self, bundle: Path, destination: str, /) -> Self: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None: ...

    def exec(
        self, command: list[str], /
    ) -> tuple[int | None, bytes | Iterator[bytes]]: ...


_Container = TypeVar("_Container", bound=WorkerdContainer)
_Pyodide = TypeVar("_Pyodide", bound=PyodideRunner)
_Result = TypeVar("_Result")

# Present only for an enabled run, including before the first measurement.
_MEASURED_TESTS = pytest.StashKey[set[str]]()


def pytest_configure(config: pytest.Config) -> None:
    if (
        config.getoption("cov_source", None)
        and not config.getoption("no_cov", False)
        and not config.getoption("collectonly")
    ):
        config.stash[_MEASURED_TESTS] = set()


def _enabled(request: pytest.FixtureRequest) -> bool:
    return (
        _MEASURED_TESTS in request.config.stash
        and request.node.get_closest_marker("no_cover") is None
        and "no_cover" not in request.fixturenames
    )


def pytest_report_header(config: pytest.Config) -> str | None:
    if _MEASURED_TESTS in config.stash:
        return "Wasm coverage enabled"
    return None


class _Run:
    def __init__(self, config: pytest.Config, host: Coverage, staging: Path) -> None:
        self.config = config
        self.host = host
        self.staging = staging
        self.shards: list[Path] = []
        self.active_pyodide: set[tuple[str, int]] = set()

    def check_runner(self) -> None:
        if hasattr(self.config, "workerinput"):
            raise pytest.UsageError("coverage-wasm requires serial pytest; use -n 0")

    def guest_paths(
        self, default_paths: dict[str, list[str]] | None = None
    ) -> tuple[list[str], list[str] | None, list[str] | None]:
        paths = cast(dict[str, list[str]], self.host.get_option("paths"))
        source, mapped = source_filters(
            cast(list[str] | None, self.host.get_option("run:source")) or [],
            paths or default_paths or {},
            self.config.invocation_params.dir,
        )
        include = mapped or cast(list[str] | None, self.host.get_option("run:include"))
        omit = cast(list[str] | None, self.host.get_option("run:omit"))
        return source, include, omit

    def save(self, payload: bytes, context: str, *, allow_empty: bool = False) -> None:
        self.check_runner()
        if not payload.startswith(b"SQLite format 3\x00"):
            raise ValueError(
                "Wasm coverage expects a native Coverage.py .coverage file"
            )

        name = f".coverage.wasm.{uuid4().hex}"
        shard = self.staging / name
        shard.write_bytes(payload)
        data = CoverageData(basename=str(shard))
        try:
            data.read()
            files = data.measured_files()
            has_lines = any(data.lines(file) for file in files)
            branch = data.has_arcs()
        finally:
            data.close(force=True)
        if allow_empty and not has_lines:
            warn(
                pytest.PytestWarning(
                    f"coverage-wasm: {context}: No Python files measured "
                    "in the Wasm guest. Check Coverage.py source filters and [paths]."
                ),
                stacklevel=2,
            )
        if not files:
            shard.unlink()
            if allow_empty:
                return
            raise RuntimeError("The Wasm coverage snapshot has no measured files")

        if branch != self.host.get_option("run:branch"):
            raise ValueError(
                "Wasm and pytest-cov must use the same branch coverage mode"
            )
        self.shards.append(shard)
        if has_lines:
            self.config.stash[_MEASURED_TESTS].add(context)


@pytest.fixture(scope="session")
def _wasm_coverage_run(
    pytestconfig: pytest.Config, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[_Run]:
    collector = Coverage.current()
    if collector is None:
        raise RuntimeError("pytest-cov did not start its Coverage.py collector")
    run = _Run(pytestconfig, collector, tmp_path_factory.mktemp("coverage-wasm"))
    yield run
    if run.shards:
        collector.combine([str(shard) for shard in run.shards], strict=True)


class WasmCoverage:
    """Collect native coverage from a guest owned by the current test fixture."""

    def __init__(self, run: _Run | None, context: str) -> None:
        self._run = run
        self.context = context

    def __call__(
        self, target: WasmCoverageTarget[_Result]
    ) -> AbstractContextManager[_Result]:
        """Open a target with the current test's coverage policy."""
        return target(self)

    @property
    def enabled(self) -> bool:
        """Whether the test opted in to Wasm coverage."""
        return self._run is not None

    def add_file(self, path: Path) -> None:
        """Collect a .coverage file from a runtime with a host-visible directory."""
        if self._run is not None:
            self._run.save(path.read_bytes(), self.context)

    def launch(
        self,
        start: Callable[[GuestCoverage | None], _Result],
        *,
        source_aliases: dict[str, list[str]] | None = None,
    ) -> _Result:
        """Give a launcher optional guest coverage and return its result unchanged."""
        run = self._run
        if run is None:
            return start(None)

        run.check_runner()
        source, include, omit = run.guest_paths(source_aliases)
        return start(
            GuestCoverage(
                context=self.context,
                branch=cast(bool, run.host.get_option("run:branch")),
                source=source,
                include=include,
                omit=omit,
                _save=lambda payload, allow_empty: run.save(
                    payload, self.context, allow_empty=allow_empty
                ),
            )
        )

    def wasi(
        self,
        argv: Iterable[str],
        *,
        grants: Iterable[Grant] = (),
        root: str | PathLike[str] | bool | None = False,
        import_path: Iterable[str] = (),
        env: Mapping[str, str] | None = None,
        stdin: bytes | bytearray | memoryview | None = None,
    ) -> Completed:
        """Run a WASI Python script and collect coverage when pytest uses --cov."""
        paths: dict[str, list[str]] = {}
        if self._run is not None and not self._run.host.get_option("paths"):
            grants = tuple(grants)
            paths = wasi.grant_paths(grants, root)
        return self.launch(
            lambda guest: wasi.run(
                argv,
                grants=grants,
                root=root,
                import_path=import_path,
                env=env,
                stdin=stdin,
                guest=guest,
                paths=paths,
            ),
            source_aliases=paths,
        )

    @contextmanager
    def wasi_script(
        self,
        argv: Iterable[str],
        *,
        grants: Iterable[Grant] = (),
        root: str | PathLike[str] | bool | None = False,
        import_path: Iterable[str] = (),
        env: Mapping[str, str] | None = None,
        stdin: bytes | bytearray | memoryview | None = None,
    ) -> Generator[Completed, None, None]:
        """Run a WASI Python script on entry and yield its completed result."""
        yield self.wasi(
            argv,
            grants=grants,
            root=root,
            import_path=import_path,
            env=env,
            stdin=stdin,
        )

    @contextmanager
    def pyodide(self, runner: _Pyodide) -> Generator[_Pyodide, None, None]:
        """Measure an initialized runner or join its existing per-test scope."""
        run = self._run
        key = (self.context, id(runner))
        if run is None or key in run.active_pyodide:
            yield runner
            return

        finish = self.launch(lambda guest: start_pyodide_coverage(runner, guest))
        assert finish is not None
        run.active_pyodide.add(key)
        try:
            yield runner
        finally:
            run.active_pyodide.remove(key)
            finish()

    def workerd_bundle(
        self, bundle: Path, *, python_modules: Path = Path("python_modules")
    ) -> Path:
        """Return the bundle to serve, using an instrumented copy under --cov."""
        return self.launch(
            lambda guest: self._workerd_bundle(bundle, python_modules, guest)
        )

    def _workerd_bundle(
        self, bundle: Path, python_modules: Path, guest: GuestCoverage | None
    ) -> Path:
        run = self._run
        if guest is None:
            return bundle
        assert run is not None
        if python_modules.is_absolute() or ".." in python_modules.parts:
            raise ValueError("python_modules must be relative to the Worker bundle")
        staged = (
            Path(mkdtemp(prefix="workerd-", dir=run.staging)) / bundle.absolute().name
        )
        copytree(bundle, staged)
        include, omit = guest.include, guest.omit
        if not guest.source and not include:
            include = ["/session/metadata/**"]
            omit = ["/session/metadata/python_modules/**", *(omit or [])]
        workerd.install(
            staged / python_modules,
            source=guest.source,
            include=include,
            omit=omit,
            context=guest.context,
            branch=guest.branch,
        )
        return staged

    def install_workerd(self, python_modules: Path, *, include: list[str]) -> None:
        """Stage a test bundle before its Worker starts."""
        if self._run is not None:
            self._run.check_runner()
            workerd.install(
                python_modules,
                include=include,
                context=self.context,
                branch=cast(bool, self._run.host.get_option("run:branch")),
            )

    def workerd(
        self,
        execute: Callable[[list[str]], tuple[int | None, bytes | Iterator[bytes]]],
        *,
        port: int = 9229,
    ) -> AbstractContextManager[None]:
        """Collect once, while the fixture still owns its running Worker."""
        return self.launch(lambda guest: workerd.collect(guest, execute, port))

    def workerd_container(
        self,
        worker: _Container,
        bundle: Path,
        *,
        python_modules: Path = Path("python_modules"),
        destination: str = "/",
        port: int = 9229,
    ) -> AbstractContextManager[_Container]:
        """Start a configured Testcontainers Worker with the bundle and collect on exit."""

        @contextmanager
        def start(guest: GuestCoverage | None) -> Generator[_Container, None, None]:
            worker.with_copy_into_container(
                self._workerd_bundle(bundle, python_modules, guest), destination
            )
            with worker as running, workerd.collect(guest, running.exec, port):
                yield running

        return self.launch(start)


@pytest.fixture
def wasm_coverage(request: pytest.FixtureRequest) -> WasmCoverage:
    run = None
    if _enabled(request):
        run = cast(_Run, request.getfixturevalue("_wasm_coverage_run"))
    return WasmCoverage(run, request.node.nodeid)


@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(
    fixturedef: pytest.FixtureDef[object], request: pytest.FixtureRequest
) -> Generator[None, object, object]:
    runner = yield
    if not _enabled(request) or not is_pyodide_fixture(
        fixturedef.argname, fixturedef.func.__module__, fixturedef.scope
    ):
        return runner

    run = cast(_Run, request.getfixturevalue("_wasm_coverage_run"))
    scope = ExitStack()
    scope.enter_context(
        WasmCoverage(run, request.node.nodeid)(
            targets.pyodide(cast(PyodideRunner, runner))
        )
    )
    request.addfinalizer(scope.close)
    return runner


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    measured = config.stash.get(_MEASURED_TESTS, None)
    if measured is None:
        return
    unit = "test" if len(measured) == 1 else "tests"
    terminalreporter.write_line(f"Wasm coverage collected from {len(measured)} {unit}")
    if config.get_verbosity() > 0:
        for nodeid in sorted(measured):
            terminalreporter.write_line(f"  {nodeid}")
