from __future__ import annotations

from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from functools import partial
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeAlias, TypeVar

from coverage_wasm.pyodide import PyodideRunner

if TYPE_CHECKING:
    from wasi_python import Completed, Grant

    from coverage_wasm._wrangler import WranglerWorker
    from coverage_wasm.pytest_plugin import WasmCoverage, WorkerdContainer


_Result = TypeVar("_Result")
_Pyodide = TypeVar("_Pyodide", bound=PyodideRunner)
_Container = TypeVar("_Container", bound="WorkerdContainer")

WasmCoverageTarget: TypeAlias = Callable[
    ["WasmCoverage"], AbstractContextManager[_Result]
]


class _LocalWorker(Protocol):
    @property
    def inspector_port(self) -> int: ...

    def execute(
        self, command: list[str], /
    ) -> tuple[int | None, bytes | Iterator[bytes]]: ...


_Worker = TypeVar("_Worker", bound=_LocalWorker)


def pyodide(runner: _Pyodide) -> WasmCoverageTarget[_Pyodide]:
    """Attach coverage to an initialized Pyodide runner."""
    return lambda coverage: coverage.pyodide(runner)


def wasi(
    argv: Iterable[str],
    *,
    grants: Iterable[Grant] = (),
    root: str | PathLike[str] | bool | None = False,
    import_path: Iterable[str] = (),
    env: Mapping[str, str] | None = None,
    stdin: bytes | bytearray | memoryview | None = None,
) -> WasmCoverageTarget[Completed]:
    """Run a WASI script and yield its completed result."""
    return lambda coverage: coverage.wasi_script(
        argv, grants=grants, root=root, import_path=import_path, env=env, stdin=stdin
    )


def workerd(
    bundle: Path,
    *,
    start: Callable[[Path], AbstractContextManager[_Worker]],
    python_modules: Path = Path("python_modules"),
) -> WasmCoverageTarget[_Worker]:
    """Start a bundle with the supplied launcher and collect before it closes."""

    @contextmanager
    def open_worker(coverage: WasmCoverage) -> Generator[_Worker, None, None]:
        prepared = coverage.workerd_bundle(bundle, python_modules=python_modules)
        with (
            start(prepared) as worker,
            coverage.workerd(worker.execute, port=worker.inspector_port),
        ):
            yield worker

    return open_worker


def workerd_container(
    worker: _Container,
    bundle: Path,
    *,
    python_modules: Path = Path("python_modules"),
    destination: str = "/",
    port: int = 9229,
) -> WasmCoverageTarget[_Container]:
    """Start a configured Testcontainers Worker and collect before shutdown."""
    return lambda coverage: coverage.workerd_container(
        worker,
        bundle,
        python_modules=python_modules,
        destination=destination,
        port=port,
    )


def wrangler(
    bundle: Path,
    *,
    executable: str | Path = "wrangler",
    config: Path = Path("wrangler.toml"),
) -> WasmCoverageTarget[WranglerWorker]:
    """Serve a prepared Worker using local Wrangler and yield its running URL."""
    from coverage_wasm._wrangler import start

    if config.is_absolute() or ".." in config.parts:
        raise ValueError("config must be relative to the Worker bundle")
    return workerd(
        bundle,
        start=partial(start, config=config, executable=executable),
        python_modules=config.parent / "python_modules",
    )
