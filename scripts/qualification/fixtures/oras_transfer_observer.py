#!/usr/bin/python3
"""Test-only wrapper around real ORAS: stop after a completed attach.

It does not fabricate successful output. The explicit fixture hash identifies
this observer; normal integration calls use the pinned official executable.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/proof/work")
args = sys.argv[1:]
mode = (ROOT / "oras-observer-mode").read_text()
if args[:2] == ["manifest", "fetch"] and (ROOT / "observed-attach.json").exists():
    if mode == "confirmation":
        raise SystemExit(1)
if not args or args[0] != "attach":
    os.execv("/opt/oras/oras", ["/opt/oras/oras", *args])
result = subprocess.run(["/opt/oras/oras", *args], capture_output=True, timeout=60)
if result.returncode:
    raise SystemExit(result.returncode)
pending = ROOT / "observed-attach.pending"
pending.write_bytes(result.stdout)
pending.replace(ROOT / "observed-attach.json")
if mode == "interruption":
    deadline = time.monotonic() + 30
    while not (ROOT / "oras-observer-release").exists():
        if time.monotonic() >= deadline:
            raise SystemExit(1)
        time.sleep(0.02)
sys.stdout.buffer.write(result.stdout)
