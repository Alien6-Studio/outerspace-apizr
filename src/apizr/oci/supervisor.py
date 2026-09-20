"""One container per invocation with bounded pipes and unconditional removal."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from pydantic import JsonValue

from apizr.execution.invocation import validate_arguments
from apizr.execution.model import Request
from apizr.execution.policy import PolicyRefused
from apizr.execution.protocol import MAX_REQUEST_BYTES, encode, frame
from apizr.execution.serialization import digest
from apizr.execution.supervisor import exchange, worker_environment

from .docker import DockerProvider
from .model import ContainerPlan, ContainerResult
from .planner import validate_plan
from .provider import ContainerProvider, ProviderError


def execute(
    runtime: ContainerPlan,
    source: bytes,
    payload: JsonValue,
    *,
    executable: bytes | None = None,
    provider: ContainerProvider | None = None,
) -> ContainerResult:
    executable = source if runtime.worker.source.kind == "python" else executable
    try:
        if executable is None:
            raise ValueError("Executable required")
        runtime = validate_plan(runtime, source, executable)
    except PolicyRefused:
        return ContainerResult(status="policy_refused")
    except (ValueError, RecursionError):
        return ContainerResult(status="binding_failed")
    try:
        encode(payload, runtime.policy.limits.max_input_bytes)
        validate_arguments(runtime.worker.interface, payload)
        request = Request(
            plan=runtime.worker, plan_digest=digest(runtime.worker), arguments=payload
        )
        data = frame(encode(request.model_dump(mode="json"), MAX_REQUEST_BYTES))
    except (ValueError, RecursionError):
        return ContainerResult(status="invalid_input")
    provider = provider or DockerProvider()
    if provider.identity != runtime.runtime.provider:
        return ContainerResult(status="backend_unavailable")
    try:
        provider.probe(runtime.runtime)
        with TemporaryDirectory(prefix="apizr-oci-") as directory:
            root = Path(directory).resolve()
            (root / "original").write_bytes(source)
            target = root / runtime.worker.executable_path
            target.parent.mkdir(parents=True)
            target.write_bytes(executable)
            # Dedicated bundle only; Linux non-root worker must be able to read it.
            for path in root.rglob("*"):
                path.chmod(0o555 if path.is_dir() else 0o444)
            root.chmod(0o755)
            name = "apizr-oci-" + uuid4().hex
            try:
                provider.create(
                    name,
                    runtime,
                    root,
                    worker_environment(runtime.policy.environment, os.environ),
                )
                result = exchange(
                    provider.command(name),
                    data,
                    root,
                    os.environ,
                    runtime.policy.limits.wall_time_ms,
                    runtime.policy.limits.max_output_bytes,
                )
                if result.status == "worker_failed":
                    state = provider.final_state(name)
                    if state is not None and state.terminal and state.oom_killed:
                        return ContainerResult(status="resource_limit")
                return ContainerResult(status=result.status, value=result.value)
            finally:
                provider.remove(name)
    except ProviderError as error:
        return ContainerResult(status=error.status)
    except OSError:
        return ContainerResult(status="worker_failed")
