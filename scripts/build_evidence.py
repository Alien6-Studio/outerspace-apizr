"""Archive the exact source, lock and SBOMs behind this CI package build."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tomllib
from pathlib import Path


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("release-evidence"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sha = command("git", "rev-parse", "HEAD")
    if os.environ.get("GITHUB_SHA", sha) != sha:
        raise ValueError("Evidence must describe the exact checked-out CI commit")
    subprocess.run(["git", "diff", "--exit-code", "HEAD"], cwd=root, check=True)
    if command(
        "git",
        "ls-files",
        "--others",
        "--exclude-standard",
        "src",
        "scripts",
        "tests",
        ".github",
    ):
        raise ValueError(
            "Untracked build or validation inputs are not release evidence"
        )
    for scope, options in (
        ("runtime", ["--no-default-groups"]),
        ("validation", ["--all-groups"]),
    ):
        subprocess.run(
            [
                "uv",
                "export",
                "--locked",
                "--offline",
                "--format",
                "cyclonedx1.5",
                "--no-emit-project",
                *options,
                "--output-file",
                str(output / f"sbom-{scope}.cdx.json"),
            ],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    for name in ("uv.lock", "pyproject.toml", "SHA256SUMS.json"):
        shutil.copyfile(root / name, output / name)
    subprocess.run(
        [
            "git",
            "archive",
            "--format=tar.gz",
            "--prefix=outerspace-apizr-source/",
            "--output",
            str(output / "source.tar.gz"),
            sha,
        ],
        cwd=root,
        check=True,
    )
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    manifest = {
        "schema": "apizr.build-evidence/v1",
        "project": project["name"],
        "version": project["version"],
        "commit": sha,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "uv": command("uv", "--version"),
        "distributions": json.loads((output / "SHA256SUMS.json").read_text()),
        "files": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.iterdir())
            if path.is_file() and path.name != "build-evidence.json"
        },
        "sbom_scope": "Universal uv.lock resolution; runtime and all validation groups. Includes platform/Python alternatives, not the exact installed graph of every user.",
    }
    (output / "build-evidence.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
