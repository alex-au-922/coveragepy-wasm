from collections.abc import Iterator
from os import environ
from pathlib import Path
from shutil import copyfile, copytree, ignore_patterns
from subprocess import run
from sys import executable
from tempfile import TemporaryDirectory

import pytest
from coverage_wasm import targets
from coverage_wasm.pytest_plugin import WasmCoverage


@pytest.fixture(scope="session")
def worker_build() -> Iterator[tuple[Path, Path]]:
    with TemporaryDirectory(prefix="workerd-example-") as temporary:
        project = Path(temporary) / "project"
        bundle = Path(temporary) / "bundle"
        copytree(
            Path(__file__).resolve().parent,
            project,
            symlinks=True,
            ignore=ignore_patterns(
                ".env*",
                ".dev.vars*",
                ".venv*",
                ".cloudflare",
                ".wrangler",
                "node_modules",
                "python_modules",
            ),
        )
        env = {**environ, "CI": "true", "WRANGLER_SEND_METRICS": "false"}
        run(["npm", "ci"], cwd=project, env=env, check=True, timeout=300)
        run(
            [
                executable,
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
        copyfile(project / "wrangler.toml", bundle / "wrangler.toml")
        (bundle / "src/python_modules").rename(bundle / "python_modules")
        yield bundle, project / "node_modules/.bin/wrangler"


@pytest.fixture
def worker_url(
    worker_build: tuple[Path, Path], wasm_coverage: WasmCoverage
) -> Iterator[str]:
    bundle, wrangler = worker_build
    with wasm_coverage(targets.wrangler(bundle, executable=wrangler)) as worker:
        yield worker.url
