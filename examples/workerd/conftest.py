from collections.abc import Iterator
from os import environ, killpg
from pathlib import Path
from shutil import copyfile, copytree
from signal import SIGKILL, SIGTERM
from socket import socket
from subprocess import STDOUT, Popen, TimeoutExpired, run
from time import monotonic, sleep
from typing import cast

import pytest
from coverage_wasm.pytest_plugin import WasmCoverage

ROOT = Path(__file__).resolve().parent
ENV = {**environ, "CI": "true", "WRANGLER_SEND_METRICS": "false"}


@pytest.fixture(scope="session")
def worker_bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    bundle = tmp_path_factory.mktemp("worker-bundle")
    run(
        ["pywrangler", "deploy", "--dry-run", "--outdir", str(bundle / "src")],
        cwd=ROOT,
        env=ENV,
        check=True,
        timeout=300,
    )
    copyfile(ROOT / "wrangler.toml", bundle / "wrangler.toml")
    (bundle / "src/python_modules").rename(bundle / "python_modules")
    return bundle


def free_ports() -> tuple[int, int]:
    with socket() as http, socket() as inspector:
        http.bind(("127.0.0.1", 0))
        inspector.bind(("127.0.0.1", 0))
        return (
            cast(tuple[str, int], http.getsockname())[1],
            cast(tuple[str, int], inspector.getsockname())[1],
        )


def wait_until_ready(worker: Popen[bytes], log: Path) -> None:
    deadline = monotonic() + 60
    while worker.poll() is None and monotonic() < deadline:
        output = log.read_text(encoding="utf-8")
        if "[ERROR]" in output:
            pytest.fail(output)
        if "Ready on http://" in output:
            return
        sleep(0.1)
    pytest.fail(log.read_text(encoding="utf-8") or "Wrangler did not start")


def execute_inspector(command: list[str]) -> tuple[int, bytes]:
    result = run(command, cwd=ROOT, capture_output=True, timeout=15)
    return result.returncode, result.stderr if result.returncode else result.stdout


@pytest.fixture
def worker_url(
    worker_bundle: Path, tmp_path: Path, wasm_coverage: WasmCoverage
) -> Iterator[str]:
    bundle = copytree(worker_bundle, tmp_path / "worker")
    wasm_coverage.install_workerd(
        bundle / "python_modules", include=["*/entrypoint.py"]
    )
    port, inspector = free_ports()
    log_path = tmp_path / "wrangler.log"
    command = [
        str(ROOT / "node_modules/.bin/wrangler"),
        "dev",
        "--config",
        str(bundle / "wrangler.toml"),
        "--local",
        "--no-bundle",
        "--ip",
        "127.0.0.1",
        "--port",
        str(port),
        "--inspector-ip",
        "127.0.0.1",
        "--inspector-port",
        str(inspector),
        "--persist-to",
        str(tmp_path / "storage"),
    ]

    with (
        log_path.open("wb") as log,
        Popen(
            command,
            cwd=ROOT,
            env=ENV,
            stdout=log,
            stderr=STDOUT,
            start_new_session=True,
        ) as worker,
    ):
        try:
            wait_until_ready(worker, log_path)
            with wasm_coverage.workerd(execute_inspector, port=inspector):
                yield f"http://127.0.0.1:{port}"
        finally:
            if worker.poll() is None:
                killpg(worker.pid, SIGTERM)
                try:
                    worker.wait(timeout=10)
                except TimeoutExpired:
                    killpg(worker.pid, SIGKILL)
                    worker.wait()
