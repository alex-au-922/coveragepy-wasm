import nox


@nox.session(python=["3.11", "3.12", "3.13", "3.14", "3.15"], venv_backend="uv")
def tests(session: nox.Session) -> None:
    """Exercise the installed pytest plugin on each supported host Python."""
    pytest = "pytest==8.4.0" if session.python == "3.11" else "pytest==9.2.0"
    session.install(*(session.posargs or ["."]), pytest)
    session.run("pytest", "-q", "tests/test_pytest_plugin.py")
