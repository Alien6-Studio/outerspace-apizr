"""Installed interpreter audit: diagnose explicit files with every effect trapped."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from apizr.onboarding import doctor


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--operator-policy", type=Path, required=True)
    parser.add_argument("--plugins-dir", type=Path)
    parser.add_argument("--delivery-request", type=Path)
    parser.add_argument("--profile", action="append", default=[])
    args = parser.parse_args()
    effects = {"writes": 0, "network": 0, "processes": 0}

    def audit(event, values):
        category = None
        if event in {
            "socket.__new__",
            "socket.connect",
            "socket.getaddrinfo",
            "socket.sendto",
        }:
            category = "network"
        elif event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
            category = "processes"
        elif event in {
            "os.mkdir",
            "os.remove",
            "os.rename",
            "os.rmdir",
            "os.chmod",
            "os.link",
            "os.symlink",
            "os.truncate",
        } or (
            event == "open"
            and values[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        ):
            category = "writes"
        if category:
            effects[category] += 1
            raise RuntimeError("doctor attempted forbidden effect")

    sys.addaudithook(audit)
    start = time.perf_counter()
    result = doctor(
        project=args.project,
        operator_policy=args.operator_policy,
        plugins_dir=args.plugins_dir,
        delivery_request=args.delivery_request,
        profiles=tuple(args.profile or ["core"]),
    )
    elapsed = time.perf_counter() - start
    assert not any(effects.values())
    print(
        json.dumps(
            {
                "doctor": result.model_dump(mode="json"),
                "effects": effects,
                "seconds": elapsed,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
