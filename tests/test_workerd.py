import os
import sys
from base64 import b64decode
from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path
from runpy import run_path
from shutil import copyfile, copytree, ignore_patterns, which
from subprocess import run
from types import ModuleType, SimpleNamespace

import pytest
from coverage import Coverage, CoverageData

from coverage_wasm import GuestCoverage, _wrangler, targets, workerd
from coverage_wasm.pytest_plugin import WasmCoverage

pytest_plugins = ["pytester"]
EXAMPLE = Path(__file__).resolve().parents[1] / "examples/workerd"


def wrangler_script(directory: Path, body: str) -> Path:
    script = directory / "wrangler"
    script.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    script.chmod(0o700)
    return script


@pytest.mark.skipif(os.name != "posix", reason="Local Wrangler requires POSIX")
@pytest.mark.parametrize("ignore_sigterm", [False, True], ids=["terminate", "kill"])
def test_wrangler_target_owns_process_and_runs_commands(
    tmp_path: Path, ignore_sigterm: bool
) -> None:
    launcher = wrangler_script(
        tmp_path,
        f"""\
import os
import signal
import time
from pathlib import Path

if {ignore_sigterm!r}:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
Path("pid").write_text(str(os.getpid()), encoding="utf-8")
time.sleep(0.3)
print("Ready on http://127.0.0.1:4321", flush=True)
time.sleep(60)
""",
    )
    wasm_coverage = WasmCoverage(None, "test_wrangler")
    target = targets.wrangler(tmp_path, executable=launcher)

    with wasm_coverage(target) as worker:
        assert worker.url == "http://127.0.0.1:4321"
        status, output = worker.execute([sys.executable, "-c", "print('snapshot')"])
        assert (status, output) == (0, b"snapshot\n")
        status, output = worker.execute(
            [sys.executable, "-c", "raise SystemExit('inspector exited')"]
        )
        assert (status, output) == (1, b"inspector exited\n")

    pid = int((tmp_path / "pid").read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.skipif(os.name != "posix", reason="Local Wrangler requires POSIX")
def test_wrangler_target_reports_early_process_exit(tmp_path: Path) -> None:
    launcher = wrangler_script(
        tmp_path, "print('invalid bundle', flush=True)\nraise SystemExit(2)\n"
    )
    wasm_coverage = WasmCoverage(None, "test_wrangler")
    target = targets.wrangler(tmp_path, executable=str(launcher))

    with (
        pytest.raises(
            RuntimeError, match="(?s)Wrangler did not become ready.*invalid bundle"
        ),
        wasm_coverage(target),
    ):
        pytest.fail("An exited Worker cannot serve a URL")


def test_wrangler_target_rejects_non_posix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_wrangler, "os", SimpleNamespace(name="nt"))
    wasm_coverage = WasmCoverage(None, "test_wrangler")
    target = targets.wrangler(tmp_path)

    with (
        pytest.raises(RuntimeError, match="support macOS and Linux"),
        wasm_coverage(target),
    ):
        pytest.fail("Wrangler cannot launch on a non-POSIX host")


@pytest.mark.parametrize("config", [Path("/wrangler.toml"), Path("../wrangler.toml")])
def test_wrangler_target_rejects_config_outside_bundle(
    tmp_path: Path, config: Path
) -> None:
    with pytest.raises(ValueError, match="config must be relative"):
        targets.wrangler(tmp_path, config=config)


@pytest.mark.parametrize(
    "core", ["SysMonitor", "CTracer"], ids=["supported", "rejected"]
)
def test_workerd_start_exports_a_native_snapshot_or_rejects_incompatible_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, core: str
) -> None:
    source = tmp_path / "entrypoint.py"
    source.write_text("message = 'Hello'\n", encoding="utf-8")
    python_modules = tmp_path / "python_modules"
    python_modules.mkdir()
    workerd.install(python_modules, include=["*/entrypoint.py"], context="test_context")
    bootstrap = python_modules / "coverage_wasm.pth"
    collector = Coverage(
        data_file=tmp_path / ".coverage.guest",
        config_file=False,
        include=[str(source)],
    )

    def set_option(name: str, value: str) -> None:
        assert (name, value) == ("run:core", "sysmon")

    def start() -> None:
        collector.get_data().add_lines({str(source): [1]})

    def local_collector(**options: object) -> Coverage:
        assert options["context"] == "test_context"
        assert options["include"] == ["*/entrypoint.py"]
        return collector

    def create_once_callable(export: Callable[[], str]) -> Callable[[], str]:
        return export

    monkeypatch.setattr(collector, "set_option", set_option)
    monkeypatch.setattr(collector, "start", start)
    monkeypatch.setattr(collector, "sys_info", lambda: [("core", core)])
    monkeypatch.setattr(workerd, "coverage", SimpleNamespace(Coverage=local_collector))

    shim = ModuleType("js")
    global_this = SimpleNamespace()
    monkeypatch.setattr(shim, "globalThis", global_this, raising=False)
    bridge = ModuleType("pyodide.ffi")
    monkeypatch.setattr(
        bridge, "create_once_callable", create_once_callable, raising=False
    )
    monkeypatch.setitem(sys.modules, "js", shim)
    monkeypatch.setitem(sys.modules, "pyodide.ffi", bridge)

    try:
        if core != "SysMonitor":
            with pytest.raises(RuntimeError, match="requires the sysmon core"):
                run_path(str(bootstrap))
            assert not hasattr(global_this, "wasmCoverage")
            return

        run_path(str(bootstrap))
        exporter = global_this.wasmCoverage
        encoded = exporter()
        assert isinstance(encoded, str)
        exported = tmp_path / ".coverage.exported"
        exported.write_bytes(b64decode(encoded, validate=True))
        data = CoverageData(basename=str(exported))
        data.read()
        assert data.lines(str(source)) == [1]
        data.close(force=True)
    finally:
        collector.get_data().close(force=True)


@pytest.mark.parametrize("streamed", [False, True], ids=["buffer", "stream"])
def test_workerd_collect_saves_snapshot_after_test_body(streamed: bool) -> None:
    received: list[bytes] = []
    guest = GuestCoverage(
        context="test_workerd",
        branch=True,
        source=[],
        include=None,
        omit=None,
        _save=lambda payload, _: received.append(payload),
    )

    with workerd.collect(
        guest,
        lambda command: (
            0,
            iter([b"native", b" snapshot"]) if streamed else b"native snapshot",
        ),
        9123,
    ):
        assert received == []
    assert received == [b"native snapshot"]


def test_workerd_collect_propagates_inspector_error() -> None:
    guest = GuestCoverage(
        context="test_workerd",
        branch=True,
        source=[],
        include=None,
        omit=None,
        _save=lambda payload, _: pytest.fail(
            f"Invalid snapshot was saved: {payload!r}"
        ),
    )

    with pytest.raises(RuntimeError, match="invalid snapshot"):
        with workerd.collect(guest, lambda command: (1, b"invalid snapshot"), 9123):
            pass


@pytest.fixture(scope="session")
def built_worker(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    if find_spec("pywrangler") is None or find_spec("workers") is None:
        pytest.skip("The Workerd example requires workers-py and workers-runtime-sdk")
    if which("node") is None or which("npm") is None:
        pytest.skip("The Workerd example requires Node and npm")

    directory = tmp_path_factory.mktemp("workerd-runtime")
    project = directory / "project"
    bundle = directory / "bundle"
    copytree(EXAMPLE / "src", project / "src", ignore=ignore_patterns("__pycache__"))
    for name in ("package.json", "package-lock.json", "wrangler.toml"):
        copyfile(EXAMPLE / name, project / name)
    (project / "pyproject.toml").write_text(
        '[project]\nname = "test-worker"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    env = {**os.environ, "CI": "true", "WRANGLER_SEND_METRICS": "false"}
    run(
        ["npm", "ci", "--no-audit", "--no-fund"],
        cwd=project,
        env=env,
        check=True,
        timeout=300,
    )
    run(
        [
            sys.executable,
            "-m",
            "pywrangler",
            "deploy",
            "--dry-run",
            "--outdir",
            str(bundle / "src"),
        ],
        cwd=project,
        env=env,
        check=True,
        timeout=300,
    )
    (bundle / "src/python_modules").rename(bundle / "python_modules")
    for name in ("package.json", "package-lock.json", "wrangler.toml"):
        copyfile(project / name, bundle / name)
    assert (bundle / "src/entrypoint.py").read_bytes() == (
        EXAMPLE / "src/entrypoint.py"
    ).read_bytes()
    return project, bundle


@pytest.mark.parametrize("runtime", ["local", "container"])
def test_real_workerd_http_collects_guest_coverage(
    pytester: pytest.Pytester, built_worker: tuple[Path, Path], runtime: str
) -> None:
    project, bundle = built_worker
    src = pytester.mkdir("src")
    source = src / "entrypoint.py"
    copyfile(EXAMPLE / "src/entrypoint.py", source)
    pytester.makepyprojecttoml(
        """\
[tool.coverage.run]
branch = true
omit = ["*/python_modules/**"]
disable_warnings = ["no-data-collected"]

[tool.coverage.paths]
source = ["src", "/session/metadata"]
"""
    )

    if runtime == "container":
        pytest.importorskip("testcontainers")
        pytester.makeconftest(
            f"""\
from pathlib import Path

import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from coverage_wasm import targets


@pytest.fixture
def worker_url(wasm_coverage):
    worker = (
        DockerContainer("node:26.13.1-bookworm")
        .with_env("CI", "true")
        .with_env("WRANGLER_SEND_METRICS", "false")
        .with_kwargs(working_dir="/bundle")
        .with_command(["sh", "-ec", "npm ci --no-audit --no-fund && "
                       "exec ./node_modules/.bin/wrangler dev --local --no-bundle "
                       "--ip 0.0.0.0 --port 8787 --inspector-port 9229"])
        .with_exposed_ports(8787)
        # The container installs npm dependencies before starting Workerd.
        .waiting_for(LogMessageWaitStrategy("Ready on http://").with_startup_timeout(300))
    )
    with wasm_coverage(targets.workerd_container(worker, Path({str(bundle)!r}))) as running:
        yield f"http://{{running.get_container_host_ip()}}:{{running.get_exposed_port(8787)}}"
"""
        )
    else:
        (pytester.path / "node_modules").symlink_to(
            project / "node_modules", target_is_directory=True
        )
        wrangler = project / "node_modules/.bin/wrangler"
        pytester.makeconftest(
            f"""\
from pathlib import Path

import pytest

from coverage_wasm import targets


@pytest.fixture
def worker_url(wasm_coverage):
    target = targets.wrangler(Path({str(bundle)!r}), executable=Path({str(wrangler)!r}))
    with wasm_coverage(target) as worker:
        yield worker.url
"""
        )

    pytester.makepyfile(
        test_worker="""\
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest


def test_routes(worker_url):
    with urlopen(f"{worker_url}/hello", timeout=15) as response:
        assert response.status == 200
        assert response.read() == b"Hello from Workerd!"
    with pytest.raises(HTTPError) as missing:
        urlopen(f"{worker_url}/missing", timeout=15)
    with missing.value as response:
        assert response.code == 404
        assert response.read() == b"Not found"
"""
    )
    result = pytester.runpytest_subprocess(
        "-p", "no:asyncio", "--cov=src", "--cov-report=html", "--cov-fail-under=100"
    )
    result.assert_outcomes(passed=1)
    assert "Wasm coverage collected from 1 test" in result.stdout.str()
    data = CoverageData(basename=str(pytester.path / ".coverage"))
    data.read()
    assert data.measured_files() == {str(source)}
    assert data.measured_contexts() == {"test_worker.py::test_routes"}
    lines = source.read_text(encoding="utf-8").splitlines()
    branch = next(i for i, line in enumerate(lines, 1) if '== "/hello"' in line)
    arcs = data.arcs(str(source))
    assert arcs is not None
    assert {(branch, branch + 1), (branch, branch + 2)} <= set(arcs)
    data.close(force=True)
    assert "entrypoint.py" in (pytester.path / "htmlcov/index.html").read_text(
        encoding="utf-8"
    )
