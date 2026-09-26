"""Run the installed sync and update proofs with inherited OS network denial for all children."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    work = args.work.resolve()
    evidence = json.loads((work / "evidence.json").read_text())
    python = Path(evidence["core_python"])
    root = python.parent.parent
    # The Homebrew installation root includes its receipt and resources too.
    if root.name == "libexec":
        root = root.parent
    command = [
        str(python),
        "-I",
        "-B",
        str(REPO / "scripts/smoke_plugin_sync.py"),
        str(work / "sync"),
        str(root),
    ]
    if sys.platform == "linux":
        command = [
            "sudo",
            "-n",
            "unshare",
            "--net",
            "--setgid",
            str(os.getgid()),
            "--setuid",
            str(os.getuid()),
            "--",
            "/usr/bin/env",
            "PATH=" + os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE=1",
            *command,
        ]
    elif sys.platform == "darwin":
        command = [
            "/usr/bin/sandbox-exec",
            "-p",
            "(version 1)(allow default)(deny network*)",
            *command,
        ]
    else:
        raise RuntimeError("Network isolation proof requires Linux or macOS")
    subprocess.run(
        command,
        cwd=work,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        check=True,
        timeout=300,
    )
    update_command = [
        value.replace("smoke_plugin_sync.py", "smoke_plugin_update.py")
        if value == str(REPO / "scripts/smoke_plugin_sync.py")
        else str(work / "update")
        if value == str(work / "sync")
        else value
        for value in command
    ]
    subprocess.run(
        update_command,
        cwd=work,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        check=True,
        timeout=300,
    )


if __name__ == "__main__":
    main()
