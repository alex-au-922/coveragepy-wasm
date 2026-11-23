import os
import re
import signal
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from socket import socket
from subprocess import STDOUT, Popen, TimeoutExpired, run
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from typing import cast

_READY = re.compile(r"Ready on (http://127\.0\.0\.1:\d+)")
_ENV = {"CI": "true", "WRANGLER_SEND_METRICS": "false"}


@dataclass(frozen=True, slots=True)
class WranglerWorker:
    url: str
    inspector_port: int

    def execute(self, command: list[str], /) -> tuple[int, bytes]:
        result = run(command, capture_output=True, timeout=20)
        return result.returncode, result.stderr if result.returncode else result.stdout


@contextmanager
def start(
    bundle: Path, *, config: Path, executable: str | Path
) -> Generator[WranglerWorker, None, None]:
    if os.name != "posix":
        raise RuntimeError("Local Wrangler targets support macOS and Linux")

    config_path = bundle.resolve() / config
    program = str(executable.resolve()) if isinstance(executable, Path) else executable
    with socket() as listener:
        listener.bind(("127.0.0.1", 0))
        inspector = cast(tuple[str, int], listener.getsockname())[1]

    with TemporaryDirectory(prefix="coverage-wasm-wrangler-") as temporary:
        directory = Path(temporary)
        log = directory / "wrangler.log"
        with log.open("wb") as output:
            worker = Popen(
                [
                    program,
                    "dev",
                    "--local",
                    "--no-bundle",
                    "--config",
                    str(config_path),
                    "--ip",
                    "127.0.0.1",
                    "--port",
                    "0",
                    "--inspector-port",
                    str(inspector),
                    "--persist-to",
                    str(directory / "storage"),
                ],
                cwd=config_path.parent,
                env={**os.environ, **_ENV},
                stdout=output,
                stderr=STDOUT,
                start_new_session=True,
            )
        try:
            deadline = monotonic() + 120
            while worker.poll() is None and monotonic() < deadline:
                if match := _READY.search(log.read_text(errors="replace")):
                    yield WranglerWorker(match[1], inspector)
                    return
                sleep(0.2)
            raise RuntimeError(
                f"Wrangler did not become ready.\n{log.read_text(errors='replace')}"
            )
        finally:
            with suppress(ProcessLookupError):
                os.killpg(worker.pid, signal.SIGTERM)
            try:
                worker.wait(timeout=6)
            except TimeoutExpired:
                with suppress(ProcessLookupError):
                    os.killpg(worker.pid, signal.SIGKILL)
                worker.wait()
