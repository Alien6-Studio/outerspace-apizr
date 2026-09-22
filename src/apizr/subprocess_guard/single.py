"""Strict OCI planning and execution over the unchanged allow-mode engine."""

from pydantic import JsonValue

from apizr.execution.policy import PolicyRefused, Subprocess
from apizr.execution.serialization import digest
from apizr.inspection import Inspection
from apizr.oci.model import (
    ContainerPlan,
    ContainerResult,
    ExecutionPolicyV2,
    RuntimeImage,
)
from apizr.oci.planner import plan as allow_plan
from apizr.oci.provider import ContainerProvider
from apizr.oci.supervisor import execute as allow_execute

from .provider import DenyDockerProvider


def relaxed(policy: ExecutionPolicyV2) -> ExecutionPolicyV2:
    policy = ExecutionPolicyV2.model_validate(policy.model_dump(mode="json"))
    if policy.subprocess.mode != "deny" or any(
        name.startswith(("LD_", "DYLD_", "PYTHON", "GLIBC_")) or name == "GCONV_PATH"
        for name in policy.environment.allow
    ):
        raise PolicyRefused("unsupported_control")
    return policy.model_copy(update={"subprocess": Subprocess(mode="allow")})


def plan(
    inspection: Inspection,
    source: bytes,
    capability: str,
    policy: ExecutionPolicyV2,
    runtime: RuntimeImage,
    *,
    executable: bytes | None = None,
) -> ContainerPlan:
    value = allow_plan(
        inspection, source, capability, relaxed(policy), runtime, executable=executable
    )
    return value.model_copy(update={"policy": policy, "policy_digest": digest(policy)})


def validate_plan(
    value: ContainerPlan, source: bytes, executable: bytes
) -> ContainerPlan:
    value = ContainerPlan.model_validate(value.model_dump(mode="json"))
    expected = plan(
        value.worker.inspection,
        source,
        value.worker.capability_id,
        value.policy,
        value.runtime,
        executable=executable,
    )
    if value != expected:
        raise ValueError("Strict container plan content binding mismatch")
    return value


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
    selected = provider or DenyDockerProvider()
    if not isinstance(selected, DenyDockerProvider):
        return ContainerResult(status="backend_unavailable")
    # The old engine validates exactly the same source, limits and resources.
    # Only this trusted adapter may pair its internal allow plan with the strict
    # provider: the public/digest-bound plan above always records deny.
    policy = relaxed(runtime.policy)
    inner = runtime.model_copy(
        update={"policy": policy, "policy_digest": digest(policy)}
    )
    return allow_execute(
        inner, source, payload, executable=executable, provider=selected
    )
