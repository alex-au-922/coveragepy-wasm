from __future__ import annotations

from collections.abc import Iterable, Mapping
from json import dumps
from os import PathLike
from pathlib import Path, PurePosixPath
from shutil import copytree, ignore_patterns
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

import coverage
from coverage import CoverageData

from coverage_wasm._guest import GuestCoverage

if TYPE_CHECKING:
    from wasi_python import Completed, Grant


_PACKAGES = "/__coverage_wasm_packages__"
_OUTPUT = "/__coverage_wasm_output__"

_COLLECT = """\
import json
import os
import runpy
import sys

from coverage import Coverage

collector = Coverage(config_file=False, **json.loads(sys.argv.pop(1)))
collector.set_option("run:core", "sysmon")
script = sys.argv.pop(1)
if not sys.flags.safe_path:
    sys.path[0] = os.path.dirname(os.path.realpath(script))
try:
    with collector.collect():
        runpy.run_path(script, run_name="__main__")
finally:
    collector.save()
"""


def grant_paths(
    grants: Iterable[Grant], root: str | PathLike[str] | bool | None
) -> dict[str, list[str]]:
    """Build path aliases for the host directories this WASI run can see."""
    mounts = {grant.guest: str(Path(grant.host).resolve()) for grant in grants}
    if isinstance(root, (str, PathLike)):
        mounts["/"] = str(Path(root).resolve())
    # WASI resolves nested mounts by the longest matching guest prefix.
    guest_dirs = sorted(
        mounts, key=lambda guest: len(PurePosixPath(guest).parts), reverse=True
    )
    return {guest: [mounts[guest], guest] for guest in guest_dirs}


def _remap(shard: Path, target: Path, paths: dict[str, list[str]]) -> Path:
    def map_path(filename: str) -> str:
        guest_file = PurePosixPath(filename)
        for host, guest in paths.values():
            if guest_file.is_relative_to(guest):
                return str(Path(host) / guest_file.relative_to(guest))
        return filename

    guest = CoverageData(basename=shard)
    host = CoverageData(basename=target)
    try:
        host.update(guest, map_path=map_path)
        host.write()
    finally:
        guest.close(force=True)
        host.close(force=True)
    return target


def run(
    argv: Iterable[str],
    *,
    grants: Iterable[Grant] = (),
    root: str | PathLike[str] | bool | None = False,
    import_path: Iterable[str] = (),
    env: Mapping[str, str] | None = None,
    stdin: bytes | bytearray | memoryview | None = None,
    guest: GuestCoverage | None = None,
    paths: dict[str, list[str]] | None = None,
) -> Completed:
    """Run a WASI Python script and collect its native coverage file if requested."""
    from wasi_python import Grant
    from wasi_python import run as run_guest

    if guest is None:
        return run_guest(
            argv,
            root=root,
            grants=grants,
            import_path=import_path,
            env=env,
            stdin=stdin,
        )

    command = list(argv)
    if not command or not command[0] or command[0].startswith("-"):
        raise ValueError(
            "WASI coverage expects a Python script path followed by arguments"
        )

    omit = guest.omit
    if paths and "/" in paths:
        # These guest paths are backed by the runtime, independently of root.
        omit = [*(omit or []), f"{_PACKAGES}/**", f"{_OUTPUT}/**", "/usr/local/lib/**"]

    with TemporaryDirectory(prefix="coverage-wasm-wasi-") as temporary:
        packages = Path(temporary) / "packages"
        assert coverage.__file__ is not None
        copytree(
            Path(coverage.__file__).parent,
            packages / "coverage",
            ignore=ignore_patterns("__pycache__", "*.so", "*.pyd"),
        )

        output = Path(temporary) / "output"
        # Coverage.py's directory probe needs a parent beneath the grant when
        # wasi-python uses its default sandbox without a root preopen.
        (output / "data").mkdir(parents=True)
        data_file = output / "data" / ".coverage"
        options = dumps(
            {
                "data_file": f"{_OUTPUT}/data/.coverage",
                "context": guest.context,
                "branch": guest.branch,
                "source": guest.source or None,
                "include": guest.include,
                "omit": omit,
            }
        )
        result = run_guest(
            ["-c", _COLLECT, options, *command],
            root=root,
            grants=[
                *grants,
                Grant(packages, _PACKAGES),
                Grant(output, _OUTPUT, writable=True),
            ],
            import_path=[_PACKAGES, *import_path],
            env=env,
            stdin=stdin,
        )
        if data_file.is_file():
            if paths:
                data_file = _remap(data_file, Path(temporary) / ".coverage", paths)
            guest.save(data_file.read_bytes())
        elif result.exit_code == 0:
            raise RuntimeError("The WASI guest did not produce a coverage file")
        return result
