"""Qualification-only audit guard, propagated into pip's isolated backend children."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ["APIZR_BUILD_PROOF_ROOT"]).resolve()
GUARD = Path(os.environ["APIZR_BUILD_NETWORK_GUARD"])
LOG = ROOT / "network-events.jsonl"


def record(value):
    with LOG.open("a") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


def audit(event, arguments):
    if event in {
        "socket.connect",
        "socket.connect_ex",
        "socket.getaddrinfo",
        "socket.sendto",
    }:
        record({"event": "network_attempt", "operation": event})
        raise RuntimeError("Network attempt during offline build qualification")
    if event == "subprocess.Popen":
        environment = arguments[3] or os.environ
        # pip deliberately replaces PYTHONPATH with its generated isolation site.
        # Preserve that isolation and append only this observer to its sitecustomize.
        for value in environment.get("PYTHONPATH", "").split(os.pathsep):
            if not value:
                continue
            site = Path(value).resolve() / "sitecustomize.py"
            if site.is_relative_to(ROOT) and site.is_file():
                contents = site.read_text()
                marker = "# apizr-build-network-observer"
                if marker not in contents:
                    with site.open("a") as stream:
                        stream.write(
                            f"\n{marker}\n"
                            f"exec(compile(open({str(GUARD)!r}).read(), {str(GUARD)!r}, 'exec'))\n"
                        )


record(
    {
        "event": "python_start",
        "program": Path(sys.argv[0]).name,
        "hook": sys.argv[1] if Path(sys.argv[0]).name == "_in_process.py" else None,
    }
)
sys.addaudithook(audit)
