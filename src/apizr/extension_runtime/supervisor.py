"""Cancellable, bounded pipes for trusted installed extensions, not a sandbox."""

import os
import selectors
import signal
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from uuid import uuid4

from pydantic import ConfigDict, Field, JsonValue, TypeAdapter

from apizr.capabilities.types import ValueModel, logical_module
from apizr.execution.protocol import SizeExceeded, encode

from .errors import (
    CleanupFailed,
    ExtensionError,
    InvalidInvocation,
    InvocationCancelled,
    InvocationTimeout,
    PluginFailed,
    PrerequisiteMissing,
    SizeLimitExceeded,
)
from .protocol import PROTOCOL, Request, Response, validate_response


class Limits(ValueModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    wall_time_ms: int = Field(default=10000, ge=1, le=600000)
    max_request_bytes: int = Field(default=1048576, ge=1, le=67108864)
    max_stdout_bytes: int = Field(default=1048576, ge=1, le=67108864)
    max_stderr_bytes: int = Field(default=65536, ge=0, le=67108864)
    cleanup_time_ms: int = Field(default=1000, ge=1, le=5000)


def _signal_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _cleanup(
    process: subprocess.Popen[bytes],
    milliseconds: int,
    *,
    group_signalled: bool = False,
) -> None:
    """Kill the owned group and reap the direct child within a separate budget.

    Unlike the existing worker helper, waiting here must be bounded. Other
    sessions and uninterruptible kernel tasks cannot be contained by this API.
    """
    failed = False
    deadline = time.monotonic() + milliseconds / 1000
    if not group_signalled:
        try:
            try:
                _signal_group(process)
            except PermissionError:
                # macOS may report EPERM for a group containing an unreaped zombie.
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=max(0, deadline - time.monotonic()))
                _signal_group(process)
        except (OSError, subprocess.TimeoutExpired):
            failed = True
    try:
        # A group signalling failure must not skip cleanup of the direct child.
        if process.poll() is None:
            process.kill()
        process.wait(timeout=max(0, deadline - time.monotonic()))
    except (OSError, subprocess.TimeoutExpired):
        failed = True
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
    if failed:
        raise CleanupFailed() from None


def _exchange(
    process: subprocess.Popen[bytes],
    payload: bytes,
    limits: Limits,
    deadline: float,
    cancel: Event | None,
    signal_group: Callable[[], None],
) -> bytes:
    assert (
        process.stdin is not None
        and process.stdout is not None
        and process.stderr is not None
    )
    streams = {
        "stdin": process.stdin,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }
    counts = {"stdout": 0, "stderr": 0}
    maxima = {"stdout": limits.max_stdout_bytes, "stderr": limits.max_stderr_bytes}
    received = bytearray()
    sent = 0
    group_signalled = False
    with selectors.DefaultSelector() as selector:
        for name, stream in streams.items():
            os.set_blocking(stream.fileno(), False)
            selector.register(
                stream,
                selectors.EVENT_WRITE if name == "stdin" else selectors.EVENT_READ,
                name,
            )
        while selector.get_map() or process.poll() is None:
            if cancel is not None and cancel.is_set():
                raise InvocationCancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise InvocationTimeout()
            if process.poll() is not None and not group_signalled:
                # A normal descendant may still hold either output stream open.
                signal_group()
                group_signalled = True
            if not selector.get_map():
                time.sleep(min(remaining, 0.05))
                continue
            for key, events in selector.select(min(remaining, 0.05)):
                if events & selectors.EVENT_WRITE:
                    try:
                        sent += os.write(key.fd, payload[sent : sent + 65536])
                    except BrokenPipeError:
                        raise PluginFailed() from None
                    if sent == len(payload):
                        selector.unregister(key.fd)
                        process.stdin.close()
                else:
                    name = key.data
                    chunk = os.read(key.fd, min(65536, maxima[name] + 1 - counts[name]))
                    if not chunk:
                        selector.unregister(key.fd)
                        streams[name].close()
                    else:
                        counts[name] += len(chunk)
                        if counts[name] > maxima[name]:
                            raise SizeLimitExceeded(
                                "stdout" if name == "stdout" else "stderr"
                            )
                        if name == "stdout":
                            received.extend(chunk)
    if process.returncode:
        raise PluginFailed()
    return bytes(received)


def invoke_extension(
    python: str | Path,
    module: str,
    operation: str,
    arguments: dict[str, JsonValue],
    *,
    limits: Limits,
    environment: Mapping[str, str],
    cancel: Event | None = None,
) -> Response:
    """Invoke an explicitly chosen installed module without importing it here.

    POSIX only. No install, discovery, shell or inherited parent environment.
    Arguments travel only on stdin; failures expose fixed codes, never content.
    Each call uses a fresh temporary CWD and a fresh session/process group.
    """
    try:
        limits = Limits.model_validate(limits.model_dump(), strict=True)
        if logical_module(module) != module:
            raise ValueError("Invalid module")
        env = TypeAdapter(dict[str, str]).validate_python(
            dict(environment), strict=True
        )
        if any(not k or "=" in k or "\0" in k or "\0" in v for k, v in env.items()):
            raise ValueError("Invalid environment")
        payload = encode(
            {
                "protocol": PROTOCOL,
                "request_id": uuid4().hex,
                "operation": operation,
                "arguments": arguments,
            },
            limits.max_request_bytes,
        )
        request = Request.model_validate_json(payload, strict=True)
    except SizeExceeded:
        raise SizeLimitExceeded("request") from None
    except (ValueError, TypeError, RecursionError):
        raise InvalidInvocation() from None
    if cancel is not None and cancel.is_set():
        raise InvocationCancelled()
    try:
        python = Path(python)
        if (
            os.name != "posix"
            or not python.is_absolute()
            or not python.is_file()
            or not os.access(python, os.X_OK)
        ):
            raise ValueError("Unavailable interpreter")
    except (OSError, ValueError, TypeError):
        raise PrerequisiteMissing() from None
    try:
        with TemporaryDirectory(prefix="apizr-extension-") as directory:
            deadline = time.monotonic() + limits.wall_time_ms / 1000
            try:
                process = subprocess.Popen(
                    [str(python), "-I", "-B", "-u", "-m", module],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=directory,
                    env=env,
                    start_new_session=True,
                    close_fds=True,
                    bufsize=0,
                )
            except OSError:
                raise PrerequisiteMissing() from None
            group_signalled = False

            def signal_group() -> None:
                nonlocal group_signalled
                _signal_group(process)
                # Record success only. A later cleanup must not signal a group
                # again after its members have become zombies (macOS EPERM).
                group_signalled = True

            try:
                raw = _exchange(
                    process, payload, limits, deadline, cancel, signal_group
                )
            finally:
                _cleanup(
                    process, limits.cleanup_time_ms, group_signalled=group_signalled
                )
            return validate_response(raw, request)
    except ExtensionError:
        raise
    except OSError:
        raise PluginFailed() from None


# Shared by trusted core installation/probe supervision; invocation behavior and
# its existing private test seams remain unchanged.
cleanup_process = _cleanup
exchange_process = _exchange
signal_process_group = _signal_group
