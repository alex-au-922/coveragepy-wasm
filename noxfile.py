from pathlib import Path
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
    audit = session.python == "3.14"
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
        *([] if audit else ["--no-default-groups"]),
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
    env = {"WASM_COVERAGE_PURE_WHEEL": coverage_wheel, "TMPDIR": str(temp)}
    if audit:
        session.run("ruff", "format", "--check", "src", "tests", "noxfile.py")
        session.run("ruff", "check", "src", "tests", "noxfile.py")
        session.run("pyright")
        env.update(
            PYTHONPATH=str(Path("tests/audit").resolve()),
            WASM_PACKAGE_COVERAGE=str(data),
        )

    try:
        session.run(
            "pytest",
            "--runtime=node",
            "-o",
            "asyncio_default_fixture_loop_scope=function",
            f"--junitxml={junit}",
            "--dist-dir=examples/pyodide/.pyodide/node_modules/pyodide",
            env=env,
        )
    finally:
        if audit and any(temp.glob(".coverage.*")):
            session.run(
                "coverage",
                "combine",
                "--rcfile=tests/audit/coverage.ini",
                f"--data-file={data}",
            )
            session.run("coverage", "html", f"--data-file={data}")

    if ElementTree.parse(junit).findall(".//testcase/skipped"):
        session.error("The end-to-end matrix requires every runtime test to run")
    if audit:
        session.run(
            "coverage",
            "report",
            f"--data-file={data}",
            "--show-missing",
            "--fail-under=100",
        )
