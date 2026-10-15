"""Use the same disposable-runner network isolation as plugin sync qualification."""

import os
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
command = [
    str(root / "core/bin/python"),
    "-I",
    "-B",
    str(Path(__file__).with_name("catalog_offline_proof.py").resolve()),
    str(root),
]
if sys.platform == "darwin":
    command = [
        "/usr/bin/sandbox-exec",
        "-p",
        "(version 1)(allow default)(deny network*)",
        *command,
    ]
elif sys.platform == "linux":
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
else:
    raise RuntimeError("Linux/macOS disposable runner required")
subprocess.run(
    command,
    cwd=root,
    check=True,
    timeout=300,
    env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
)
