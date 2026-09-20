"""Bounded pipe supervision and OS process termination, not a sandbox."""

import os
import selectors
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import JsonValue

from .invocation import validate_arguments
from .model import ExecutionResult, Request, RuntimePlan
from .planner import validate_plan
from .policy import Environment, PolicyRefused
from .protocol import (
    MAX_REQUEST_BYTES,
    ProtocolError,
    SizeExceeded,
    decode,
    encode,
    frame,
    size,
)
from .serialization import digest


def worker_environment(
    policy: Environment, parent: Mapping[str, str]
) -> dict[str, str]:
    return (
        dict(parent)
        if policy.inherit
        else {name: parent[name] for name in policy.allow if name in parent}
    )


def kill_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        # macOS can report EPERM for a group containing only an unreaped zombie.
        # Reap the direct child, then retry; a live inaccessible group still fails.
        if process.poll() is None:
            process.kill()
        process.wait()
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait()


def exchange(
    command: Sequence[str],
    payload: bytes,
    root: Path,
    environment: Mapping[str, str],
    wall_time_ms: int,
    output_limit: int,
) -> ExecutionResult:
    deadline = time.monotonic() + wall_time_ms / 1000
    process = subprocess.Popen(
        list(command),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=root,
        env=environment,
        start_new_session=True,
        close_fds=True,
        bufsize=0,
    )
    sent = 0
    received = bytearray()
    try:
        assert process.stdin is not None and process.stdout is not None
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdin.fileno(), False)
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE)
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return ExecutionResult(status="timeout")
                for key, events in selector.select(min(remaining, 0.05)):
                    if events & selectors.EVENT_WRITE:
                        try:
                            sent += os.write(key.fd, payload[sent : sent + 65536])
                        except BrokenPipeError:
                            return ExecutionResult(status="worker_failed")
                        if sent == len(payload):
                            selector.unregister(key.fileobj)
                            process.stdin.close()
                    else:
                        chunk = os.read(
                            key.fd, min(65536, output_limit + 9 - len(received))
                        )
                        if not chunk:
                            selector.unregister(key.fileobj)
                            process.stdout.close()
                        else:
                            received.extend(chunk)
                            if len(received) > output_limit + 8:
                                return ExecutionResult(status="output_limit")
                            if len(received) >= 8:
                                size(bytes(received[:8]), output_limit)
                if process.poll() is not None:
                    # Close inherited pipes held by ordinary descendants as well.
                    kill_group(process)
            try:
                code = process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                return ExecutionResult(status="timeout")
            if code:
                return ExecutionResult(status="worker_failed")
        result = ExecutionResult.model_validate(decode(bytes(received), output_limit))
        if result.status != "success" and result.value is not None:
            return ExecutionResult(status="worker_failed")
        return result
    except SizeExceeded:
        return ExecutionResult(status="output_limit")
    except (OSError, ValueError, ProtocolError, RecursionError):
        return ExecutionResult(status="worker_failed")
    finally:
        kill_group(process)
        if process.stdin is not None:
            process.stdin.close()
        if process.stdout is not None:
            process.stdout.close()


def execute(
    runtime: RuntimePlan,
    source: bytes,
    payload: JsonValue,
    *,
    executable: bytes | None = None,
) -> ExecutionResult:
    executable = source if runtime.source.kind == "python" else executable
    try:
        if executable is None:
            raise ValueError("Executable required")
        validated = validate_plan(runtime, source, executable)
    except PolicyRefused:
        return ExecutionResult(status="policy_refused")
    except (ValueError, RecursionError):
        return ExecutionResult(status="binding_failed")
    try:
        encode(payload, validated.policy.limits.max_input_bytes)
        validate_arguments(validated.interface, payload)
        request = Request(
            plan=validated, plan_digest=digest(validated), arguments=payload
        )
        data = frame(encode(request.model_dump(mode="json"), MAX_REQUEST_BYTES))
    except (ValueError, RecursionError):
        return ExecutionResult(status="invalid_input")
    try:
        with TemporaryDirectory(prefix="apizr-execute-") as directory:
            root = Path(directory).resolve()
            (root / "original").write_bytes(source)
            target = root / validated.executable_path
            target.parent.mkdir(parents=True)
            target.write_bytes(executable)
            return exchange(
                [sys.executable, "-I", "-m", "apizr.execution.worker"],
                data,
                root,
                worker_environment(validated.policy.environment, os.environ),
                validated.policy.limits.wall_time_ms,
                validated.policy.limits.max_output_bytes,
            )
    except OSError:
        return ExecutionResult(status="worker_failed")
