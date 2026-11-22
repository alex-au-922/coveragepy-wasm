import os
import re
import tomllib
from pathlib import Path
from subprocess import check_output, run


def main() -> None:
    previous = check_output(
        ["git", "show", f"{os.environ['PREVIOUS_SHA']}:pyproject.toml"], text=True
    )
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    if version == tomllib.loads(previous)["project"]["version"]:
        print("The package version is unchanged.")
        return

    number = r"(?:0|[1-9][0-9]*)"
    match = re.fullmatch(rf"({number}\.{number}\.{number})(?:rc({number}))?", version)
    if match is None:
        raise SystemExit("Use a major.minor.patch version or a release candidate")
    base, candidate = match.groups()
    tag = f"v{base}-rc.{candidate}" if candidate is not None else f"v{base}"

    ref = run(
        ["git", "rev-parse", "--quiet", "--verify", f"refs/tags/{tag}^{{commit}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if ref.returncode not in (0, 1):
        ref.check_returncode()
    tagged = ref.stdout.strip()
    if tagged and tagged != os.environ["GITHUB_SHA"]:
        print(f"{tag} is already allocated to {tagged}.")
        return

    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as outputs:
        print(f"tag={tag}", file=outputs)
        print(f"create_tag={str(not tagged).lower()}", file=outputs)
        print(f"prerelease={str(candidate is not None).lower()}", file=outputs)


if __name__ == "__main__":
    main()
