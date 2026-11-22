from base64 import b64decode
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Protocol, runtime_checkable
from uuid import uuid4

from coverage_wasm._guest import GuestCoverage


@runtime_checkable
class PyodideRunner(Protocol):
    """Host-side interface for a running pytest-pyodide fixture."""

    def load_package(self, packages: str) -> None: ...

    def run(self, code: str) -> object: ...


def is_pyodide_fixture(name: str, module: str, scope: str) -> bool:
    return (
        module == "pytest_pyodide.fixture"
        and scope == "function"
        and name
        in {
            "selenium",
            "selenium_jspi",
            "selenium_jspi_worker",
            "selenium_standalone",
            "selenium_worker",
        }
    )


def source_filters(
    source: list[str], paths: dict[str, list[str]], root: Path
) -> tuple[list[str], list[str]]:
    """Translate mapped source directories into guest file patterns."""
    directories = {name: (root / name).resolve() for name in source}
    mapped: list[str] = []
    for local, *aliases in (group for group in paths.values() if group):
        host = (root / local).resolve()
        for directory in directories.values():
            if not directory.is_dir():
                continue
            if directory.is_relative_to(host):
                suffix = directory.relative_to(host).as_posix()
            elif host.is_relative_to(directory):
                suffix = "."
            else:
                continue
            mapped.extend(
                (PurePosixPath(alias) / suffix / "**").as_posix() for alias in aliases
            )

    if not mapped:
        return source, []

    patterns = list(mapped)
    for name, directory in directories.items():
        if directory.is_dir():
            patterns.append((PurePosixPath(name) / "**").as_posix())
        else:
            module = name.replace(".", "/")
            patterns.extend((f"*/{module}.py", f"*/{module}/**"))
    # Pyodide may create these directories after the test starts. Coverage.py
    # treats a missing source directory as a module name, while globs still match.
    return [], list(dict.fromkeys(patterns))


def start_pyodide_coverage(
    runner: object, guest: GuestCoverage | None
) -> Callable[[], None] | None:
    """Measure a running pytest-pyodide fixture until its snapshot is requested."""
    if guest is None:
        return None
    if not isinstance(runner, PyodideRunner):
        raise TypeError("Coverage requires an initialized pytest-pyodide runner")

    runner.load_package("coverage")
    data_file = f"/tmp/.coverage-wasm-{uuid4().hex}"
    start = f"""\
import sys
from coverage import Coverage

stdlib_zip = f"*/python{{sys.version_info.major}}{{sys.version_info.minor}}.zip/*"
Coverage(
    data_file={data_file!r},
    config_file=False,
    branch={guest.branch!r},
    source={guest.source or None!r},
    include={guest.include or None!r},
    omit=[stdlib_zip, *{guest.omit or []!r}],
    context={guest.context!r},
).start()
"""
    runner.run(f"exec({start!r}, {{}})")

    def finish() -> None:
        stop = f"""\
from base64 import b64encode
from pathlib import Path
from coverage import Coverage

collector = Coverage.current()
if collector is None or collector.get_data().data_filename() != {data_file!r}:
    raise RuntimeError("The pytest-pyodide coverage collector is no longer active")
collector.stop()
collector.save()
data_file = Path({data_file!r})
payload = b64encode(data_file.read_bytes()).decode("ascii")
data_file.unlink()
"""
        payload = runner.run(
            "_coverage_wasm_namespace = {}\n"
            f"exec({stop!r}, _coverage_wasm_namespace)\n"
            "globals().pop('_coverage_wasm_namespace')['payload']"
        )
        if not isinstance(payload, str):
            raise TypeError(
                "The pytest-pyodide runner returned an invalid coverage snapshot"
            )
        guest.save(b64decode(payload, validate=True), allow_empty=True)

    return finish
