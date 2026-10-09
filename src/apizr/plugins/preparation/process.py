"""Bounded process groups for the explicit interpreter, resolver and wheel transfer."""

import os
import selectors
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from apizr.extension_runtime.errors import CleanupFailed
from apizr.extension_runtime.supervisor import cleanup_process, signal_process_group

from .models import MAX_DIAGNOSTIC_BYTES, MAX_RESOLVER_BYTES, Control, PreparationError


@dataclass(frozen=True)
class Completed:
    code: int
    stdout: bytes
    stderr: bytes


def run(
    arguments: list[str],
    work: Path,
    control: Control,
    *,
    environment: Mapping[str, str] | None = None,
    max_stdout: int = MAX_RESOLVER_BYTES,
) -> Completed:
    control.check()
    try:
        child = subprocess.Popen(
            arguments,
            cwd=work,
            env=dict(environment or {}),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            close_fds=True,
            bufsize=0,
            umask=0o077,
        )
    except OSError:
        raise PreparationError("preparation_tool_unavailable") from None
    signalled = False
    output = {"stdout": bytearray(), "stderr": bytearray()}
    maxima = {"stdout": max_stdout, "stderr": MAX_DIAGNOSTIC_BYTES}
    try:
        assert child.stdout is not None and child.stderr is not None
        with selectors.DefaultSelector() as selector:
            for name, stream in (("stdout", child.stdout), ("stderr", child.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map() or child.poll() is None:
                control.check()
                if child.poll() is not None and not signalled:
                    signal_process_group(child)
                    signalled = True
                remaining = min(0.05, max(0, control.deadline - time.monotonic()))
                if not selector.get_map():
                    time.sleep(remaining)
                    continue
                for key, _ in selector.select(remaining):
                    name = key.data
                    chunk = os.read(
                        key.fd, min(65536, maxima[name] + 1 - len(output[name]))
                    )
                    if not chunk:
                        selector.unregister(key.fd)
                    else:
                        output[name].extend(chunk)
                        if len(output[name]) > maxima[name]:
                            raise PreparationError("resolver_output_too_large")
        control.check()
        return Completed(
            child.returncode, bytes(output["stdout"]), bytes(output["stderr"])
        )
    finally:
        try:
            cleanup_process(child, 2000, group_signalled=signalled)
        except CleanupFailed:
            raise PreparationError("preparation_cleanup_failed") from None
