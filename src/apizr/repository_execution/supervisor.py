"""Fresh copied repository invocation roots using the existing pipe supervisor."""

import os
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from uuid import uuid4

from pydantic import JsonValue

from apizr.execution.invocation import validate_arguments
from apizr.execution.model import ExecutionResult
from apizr.execution.policy import PolicyRefused, check_controls, local_capabilities
from apizr.execution.protocol import MAX_REQUEST_BYTES, encode, frame
from apizr.execution.serialization import canonical_bytes, digest
from apizr.execution.supervisor import exchange, worker_environment
from apizr.oci.model import ContainerResult
from apizr.oci.provider import ProviderError

from .docker import RepositoryDockerProvider
from .model import RepositoryContainerPlan, RepositoryRuntimePlan, Request
from .planner import validate_plan, validate_sources


def execute(
    plan: RepositoryRuntimePlan | RepositoryContainerPlan,
    exposure: bytes,
    sources: Mapping[str, bytes],
    payload: JsonValue,
    *,
    runtime_files: Mapping[str, bytes] | None = None,
    provider: RepositoryDockerProvider | None = None,
) -> ExecutionResult | ContainerResult:
    container = isinstance(plan, RepositoryContainerPlan)
    result_type = ContainerResult if container else ExecutionResult
    worker = plan.worker if isinstance(plan, RepositoryContainerPlan) else plan
    sources = dict(sources)
    try:
        if not container and worker.execution_context != "local-process":
            raise PolicyRefused("unsupported_control")
        validate_plan(plan, exposure)
        validate_sources(worker.repository_interface, sources)
        check_controls(worker.policy, local_capabilities())
    except PolicyRefused:
        return result_type(status="policy_refused")
    except (ValueError, RecursionError):
        return result_type(status="binding_failed")
    try:
        encode(payload, worker.policy.limits.max_input_bytes)
        validate_arguments(worker.interface, payload)
        data = frame(
            encode(
                Request(
                    plan=worker, plan_digest=digest(worker), arguments=payload
                ).model_dump(mode="json"),
                MAX_REQUEST_BYTES,
            )
        )
    except (ValueError, RecursionError):
        return result_type(status="invalid_input")
    try:
        selected_provider = provider or RepositoryDockerProvider()
        if isinstance(plan, RepositoryContainerPlan):
            if selected_provider.identity != plan.runtime.provider:
                return ContainerResult(status="backend_unavailable")
            selected_provider.probe(plan.runtime)
        with TemporaryDirectory(prefix="apizr-repository-") as directory:
            root = Path(directory).resolve()
            files = {
                **sources,
                "repository-interface.json": canonical_bytes(
                    worker.repository_interface
                ),
                "exposure-plan.json": exposure,
            }
            for name, content in (runtime_files or {}).items():
                entry = PurePosixPath(name)
                if (
                    str(entry) != name
                    or entry.is_absolute()
                    or ".." in entry.parts
                    or "\\" in name
                    or not (
                        name.startswith("apizr_governed/")
                        or name == "execution/worker.py"
                    )
                ):
                    raise ValueError("Unexpected worker artifact")
                files[name] = content
            for name, content in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            environment = worker_environment(worker.policy.environment, os.environ)
            if isinstance(plan, RepositoryContainerPlan):
                for path in root.rglob("*"):
                    path.chmod(0o555 if path.is_dir() else 0o444)
                root.chmod(0o755)
                name = "apizr-oci-" + uuid4().hex
                try:
                    selected_provider.create_repository(name, plan, root, environment)
                    result = exchange(
                        selected_provider.command(name),
                        data,
                        root,
                        os.environ,
                        plan.policy.limits.wall_time_ms,
                        plan.policy.limits.max_output_bytes,
                    )
                    if result.status == "worker_failed":
                        state = selected_provider.final_state(name)
                        if state is not None and state.terminal and state.oom_killed:
                            return ContainerResult(status="resource_limit")
                    return ContainerResult(status=result.status, value=result.value)
                finally:
                    selected_provider.remove(name)
            command = [sys.executable, "-I", "-B"]
            if runtime_files is None:
                command += ["-m", "apizr.repository_execution.worker"]
            else:
                command += [str(root / "execution/worker.py")]
            return exchange(
                command,
                data,
                root,
                environment,
                worker.policy.limits.wall_time_ms,
                worker.policy.limits.max_output_bytes,
            )
    except ProviderError as error:
        return ContainerResult(status=error.status)
    except (OSError, ValueError, RecursionError):
        return result_type(status="worker_failed")
