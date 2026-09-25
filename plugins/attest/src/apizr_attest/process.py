"""Bounded native calls inside the existing extension runtime's owned group.

Public Python operations and the CLI both enter through invoke_extension. Its
cleanup owns this process and ordinary descendants, including on SIGKILL.
"""

import os
import selectors
import subprocess
import time
from pathlib import Path

from .model import AttestError


def run(
    executable: Path, arguments: list[str], work: Path, deadline: float, limit: int
) -> bytes:
    if time.monotonic() >= deadline:
        raise AttestError("attest_timeout")
    process = None
    try:
        process = subprocess.Popen(
            [str(executable), *arguments],
            cwd=work,
            env={
                "HOME": str(work),
                "PATH": os.defpath,
                "TMPDIR": str(work),
                "LC_ALL": "C",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            bufsize=0,
        )
        assert process.stdout is not None and process.stderr is not None
        output = bytearray()
        count = 0
        with selectors.DefaultSelector() as selector:
            for stream in (process.stdout, process.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map() or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AttestError("attest_timeout")
                for key, _ in selector.select(min(0.05, remaining)):
                    data = os.read(key.fd, min(65536, limit + 1 - count))
                    if not data:
                        selector.unregister(key.fileobj)
                    else:
                        count += len(data)
                        if count > limit:
                            raise AttestError("attest_output_limit")
                        if key.fileobj is process.stdout:
                            output.extend(data)
        if process.returncode:
            raise AttestError("attest_command_failed")
        return bytes(output)
    except OSError:
        raise AttestError("attest_unavailable") from None
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=2)
            finally:
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
