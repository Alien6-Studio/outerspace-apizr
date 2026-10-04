"""Refuse publication unless the tag, exact CI build and required gates agree."""

import argparse
import json
import os
import re
import subprocess
import tomllib
import urllib.error
import urllib.parse
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


def qualification_branch(version: str) -> str:
    """Explicit release lines; a new branch never authorizes a new version."""
    if version in {"0.2.0", "0.2.1", "0.3.0", "0.4.0", "0.4.0rc1"}:
        return "master"  # Historical evidence retains its original identity.
    if re.fullmatch(r"0\.4\.1(?:rc[1-9]\d*)?", version):
        return "release/0.4.1"
    if version in {"0.4.2rc1", "0.4.2rc2", "0.4.2"}:
        return "release/0.4.2"
    if version == "0.4.3":
        return "release/0.4.3"
    if version == "0.4.4":
        return "master"
    raise ValueError("No authorized qualification branch for this version")


def validate_run(run: dict, sha: str, workflow: str, branch: str = "master") -> None:
    if branch not in {"master", "release/0.4.1", "release/0.4.2", "release/0.4.3"}:
        raise ValueError("Unexpected qualification branch")
    expected = {
        "head_sha": sha,
        "head_branch": branch,
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "path": f".github/workflows/{workflow}",
    }
    if any(run.get(key) != value for key, value in expected.items()):
        raise ValueError(
            f"Release requires successful {branch} push run of {workflow} at {sha}"
        )
    if run.get("repository", {}).get("full_name") != REPOSITORY:
        raise ValueError("Unexpected CI repository")


def validate_release_tag(tag: str, version: str, sha: str) -> None:
    """Bind a resumed publication to the existing remote tag, never retag it."""
    if tag != f"v{version}":
        raise ValueError("Release tag must match the source version")
    target = github(f"git/ref/tags/{tag}")["object"]
    for _ in range(5):
        if target["type"] == "commit":
            if target["sha"] != sha:
                raise ValueError("Checkout must equal the immutable release tag")
            return
        if target["type"] != "tag":
            break
        target = github(f"git/tags/{target['sha']}")["object"]
    raise ValueError("Release tag must resolve to a commit")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument(
        "--release-tag", help="Existing artifact tag to publish without rebuilding"
    )
    parser.add_argument("--coordinated", action="store_true")
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Read-only checks without a tag; never publication authorization",
    )
    args = parser.parse_args()
    project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
    version = project["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:rc[1-9]\d*)?", version):
        raise ValueError("Expected final or release-candidate version")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if args.release_tag:
        if args.preflight or not re.fullmatch(
            rf"refs/tags/v{re.escape(version)}(?:-publish[1-9]\d*)?",
            os.environ.get("GITHUB_REF", ""),
        ):
            raise ValueError("Publication must run on a matching protected version tag")
        validate_release_tag(args.release_tag, version, sha)
    elif not args.preflight:
        if os.environ.get("GITHUB_REF") != f"refs/tags/v{version}":
            raise ValueError("Dispatch must run on the matching immutable version tag")
        if sha != os.environ.get("GITHUB_SHA"):
            raise ValueError("Checkout must equal the dispatched tag commit")
    if not args.preflight and version in {"0.4.0", "0.4.0rc1"}:
        raise ValueError(
            "0.4.0 publication is closed; preserve published 0.4.0rc1 unchanged"
        )
    branch = qualification_branch(version)
    validate_run(github(f"actions/runs/{args.run_id}"), sha, "ci.yml", branch)
    if branch != "master" or version == "0.4.4":
        source = github("branches/" + urllib.parse.quote(branch, safe=""))
        if source.get("protected") is not True:
            raise ValueError("Release qualification branch must be protected")
    if args.coordinated:
        jobs = github(f"actions/runs/{args.run_id}/jobs?per_page=100")["jobs"]
        expected_jobs = {
            "distributions",
            "release-delivery",
            *(
                f"release-target ({system}, {python})"
                for system, python in (
                    ("ubuntu-latest", "3.11"),
                    ("ubuntu-latest", "3.12"),
                    ("ubuntu-latest", "3.13"),
                    ("ubuntu-latest", "3.14"),
                    ("macos-latest", "3.11"),
                    ("macos-latest", "3.14"),
                )
            ),
        }
        if version == "0.4.4":
            expected_jobs.update({"provenance", "release-assets"})
        for name in expected_jobs:
            selected_jobs = [job for job in jobs if job["name"] == name]
            if len(selected_jobs) != 1 or selected_jobs[0]["conclusion"] != "success":
                raise ValueError(f"Missing coordinated qualification: {name}")
        for name in ("oci", "attest", "mcp"):
            plugin = tomllib.loads(Path("plugins", name, "pyproject.toml").read_text())[
                "project"
            ]
            if plugin["version"] != version:
                raise ValueError("Uncoordinated distribution versions")
    verified_runs = {}
    for workflow in ("security.yml", "mkdocs.yaml"):
        runs = github(
            f"actions/workflows/{workflow}/runs?head_sha={sha}&event=push&per_page=100"
        )["workflow_runs"]
        # A later failed/in-progress attempt must not be hidden by an older green one.
        if not runs:
            raise ValueError(f"Missing {workflow} verification")
        selected = max(runs, key=lambda run: run["id"])
        validate_run(selected, sha, workflow, branch)
        verified_runs[workflow] = int(selected["id"])
    if not args.source_only:
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
            if args.release_tag:
                output.write(
                    f"release_sha={sha}\nrelease_tag={args.release_tag}\nrelease_version={version}\n"
                )
            output.write(f"source_ref=refs/heads/{branch}\n")
            output.write(f"security_run_id={verified_runs['security.yml']}\n")
    if args.preflight:
        print("Preflight only: no tag, upload or publication authorization")
    print(
        f"Verified {version}, {sha}, CI run {args.run_id}, Security, Documentation"
        + (
            "; public artifact comparison required"
            if args.source_only
            else ", and unused PyPI version"
        )
    )


if __name__ == "__main__":
    main()
