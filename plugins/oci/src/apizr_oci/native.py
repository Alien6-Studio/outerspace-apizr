"""Bounded native calls inside the existing extension runtime's owned group.

Public Python operations and the CLI both enter through invoke_extension. Its
cleanup owns this process and ordinary descendants, including on SIGKILL.
"""

import os
import selectors
import subprocess
import time
from pathlib import Path

from .model import BuildError


def run(
    executable: Path,
    arguments: list[str],
    work: Path,
    deadline: float,
    limit: int,
    *,
    stdout_limit: int | None = None,
) -> bytes:
    if time.monotonic() >= deadline:
        raise BuildError("native_timeout")
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
                    raise BuildError("native_timeout")
                for key, _ in selector.select(min(0.05, remaining)):
                    available = limit + 1 - count
                    if key.fileobj is process.stdout and stdout_limit is not None:
                        available = min(available, stdout_limit + 1 - len(output))
                    data = os.read(key.fd, min(65536, available))
                    if not data:
                        selector.unregister(key.fileobj)
                    else:
                        count += len(data)
                        if count > limit:
                            raise BuildError("native_output_limit")
                        if key.fileobj is process.stdout:
                            output.extend(data)
                            if stdout_limit is not None and len(output) > stdout_limit:
                                raise BuildError("native_output_limit")
        if process.returncode:
            raise BuildError("native_command_failed")
        return bytes(output)
    except OSError:
        raise BuildError("native_unavailable") from None
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
