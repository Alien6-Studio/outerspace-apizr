#!/usr/bin/python3
"""Bounded build-only diagnostics for the disposable OCI registry fixture."""

import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    args = sys.argv[1:]
    if not args or args[0] != "build":
        os.execv("/usr/local/bin/docker", ["/usr/local/bin/docker", *args])
    with subprocess.Popen(
        ["/usr/local/bin/docker", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as child:
        assert child.stdout is not None
        count = 0
        with Path("/proof/work/build-diagnostic.log").open("ab") as log:
            while raw := child.stdout.read(4096):
                count += len(raw)
                if count > 1048576:
                    child.kill()
                    break
                log.write(raw)
                log.flush()
                sys.stderr.buffer.write(raw)
                sys.stderr.buffer.flush()
        code = child.wait()
    if code == 0:
        saved = {}
        for flag in ("--iidfile", "--metadata-file"):
            if flag in args:
                saved[flag] = Path(args[args.index(flag) + 1]).read_text()
        Path("/proof/work/build-observation.json").write_text(json.dumps(saved))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
