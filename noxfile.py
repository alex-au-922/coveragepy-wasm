from pathlib import Path
from shutil import copyfile
from xml.etree import ElementTree

import nox


@nox.session(
    python=["3.11", "3.12", "3.13", "3.14", "3.15"],
    venv_backend="uv",
    allow_parallel=True,
)
def tests(session: nox.Session) -> None:
    """Exercise the installed wheel in real Wasm runtimes on each host Python."""
    wheel, coverage_wheel = session.posargs
    session.run(
        "uv",
        "sync",
        "--locked",
        "--active",
        "--group",
        "wasm-test",
        "--no-install-project",
        "--python",
        str(session.python),
        "--no-default-groups",
        external=True,
    )
    session.install("--no-deps", wheel)
    if session.python == "3.11":
        session.install("--no-deps", "pytest==8.4.0")

    # Keep pytester's projects outside the repository's pytest configuration.
    temp = Path(coverage_wheel).resolve().parent / f"python-{session.python}"
    temp.mkdir()
    junit = temp / "tests.xml"
    data = temp / ".coverage"
    session.run(
        "pytest",
        "-x",
        "--runtime=node",
        "-o",
        "asyncio_default_fixture_loop_scope=function",
        f"--junitxml={junit}",
        "--dist-dir=examples/pyodide/.pyodide/node_modules/pyodide",
        env={
            "PYTHONPATH": str(Path("tests").resolve()),
            "TMPDIR": str(temp),
            "WASM_COVERAGE_PURE_WHEEL": coverage_wheel,
            "WASM_PACKAGE_COVERAGE": str(data),
        },
    )
    if ElementTree.parse(junit).findall(".//testcase/skipped"):
        session.error("The end-to-end matrix requires every runtime test to run")

    session.run("coverage", "combine", f"--data-file={data}")
    matrix = Path(".coverage-matrix")
    matrix.mkdir(exist_ok=True)
    copyfile(data, matrix / f".coverage.{session.python}")
