"""Audit every resolved dependency variant in uv.lock, including tooling groups."""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write pip-audit JSON to this path")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="apizr-audit-") as directory:
        subprocess.run(
            [
                "uv",
                "export",
                "--locked",
                "--all-groups",
                "--no-emit-project",
                "--format",
                "pylock.toml",
                "--output-file",
                str(Path(directory) / "pylock.toml"),
            ],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        command = [
            sys.executable,
            "-m",
            "pip_audit",
            "--locked",
            directory,
            "--strict",
            "--progress-spinner",
            "off",
        ]
        if args.output:
            command.extend(["--format", "json", "--output", str(args.output.resolve())])
        return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
