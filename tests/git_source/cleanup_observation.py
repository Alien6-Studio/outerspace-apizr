"""Test-only syscall diagnostics: never record command arguments or environments."""

import functools
import json
import os
import subprocess
import sys
from unittest.mock import patch


def observe(call, function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (OSError, subprocess.TimeoutExpired) as error:
            process = (
                args[0] if args and isinstance(args[0], subprocess.Popen) else None
            )
            print(
                "cleanup observation: "
                + json.dumps(
                    {
                        "call": call,
                        "error": type(error).__name__,
                        "errno": getattr(error, "errno", None),
                        "returncode": getattr(process, "returncode", None),
                    }
                ),
                file=sys.stderr,
                flush=True,
            )
            raise

    return wrapped


def main():
    from apizr.cli import main as cli

    with (
        patch.object(os, "killpg", observe("killpg", os.killpg)),
        patch.object(subprocess.Popen, "kill", observe("kill", subprocess.Popen.kill)),
        patch.object(subprocess.Popen, "wait", observe("wait", subprocess.Popen.wait)),
    ):
        return cli(sys.argv[1:])
