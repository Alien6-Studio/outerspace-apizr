"""Refuse publication unless the tag, exact CI build and required gates agree."""

import argparse
import json
import os
import re
import subprocess
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

REPOSITORY = "Alien6-Studio/outerspace-apizr"


def github(path: str):
    result = subprocess.run(
        ["gh", "api", f"repos/{REPOSITORY}/{path}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def validate_run(run: dict, sha: str, workflow: str) -> None:
    expected = {
        "head_sha": sha,
        "head_branch": "master",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "path": f".github/workflows/{workflow}",
    }
    if any(run.get(key) != value for key, value in expected.items()):
        raise ValueError(
            f"Release requires successful master push run of {workflow} at {sha}"
        )
    if run.get("repository", {}).get("full_name") != REPOSITORY:
        raise ValueError("Unexpected CI repository")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
    version = project["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected stable release version")
    if os.environ.get("GITHUB_REF") != f"refs/tags/v{version}":
        raise ValueError("Dispatch must run on the matching immutable version tag")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if sha != os.environ.get("GITHUB_SHA"):
        raise ValueError("Checkout must equal the dispatched tag commit")
    validate_run(github(f"actions/runs/{args.run_id}"), sha, "ci.yml")
    verified_runs = {}
    for workflow in ("security.yml", "mkdocs.yaml"):
        runs = github(
            f"actions/workflows/{workflow}/runs?head_sha={sha}&event=push&per_page=100"
        )["workflow_runs"]
        # A later failed/in-progress attempt must not be hidden by an older green one.
        if not runs:
            raise ValueError(f"Missing {workflow} verification")
        selected = max(runs, key=lambda run: run["id"])
        validate_run(selected, sha, workflow)
        verified_runs[workflow] = int(selected["id"])
    try:
        urllib.request.urlopen(
            f"https://pypi.org/pypi/{project['name']}/{version}/json", timeout=30
        ).close()
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    else:
        raise ValueError(
            "Version already exists on PyPI; never overwrite or skip existing files"
        )
    if args.github_output:
        with args.github_output.open("a") as output:
            output.write(f"security_run_id={verified_runs['security.yml']}\n")
    print(
        f"Verified {version}, {sha}, CI run {args.run_id}, Security, Documentation, and unused PyPI version"
    )


if __name__ == "__main__":
    main()
