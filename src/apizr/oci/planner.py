"""Pure planning: no Docker discovery, source execution or image acquisition."""

from apizr.execution.planner import plan as worker_plan
from apizr.execution.policy import ExecutionPolicy, PolicyRefused
from apizr.execution.serialization import digest
from apizr.inspection import Inspection

from .model import ContainerPlan, ExecutionPolicyV2, RuntimeImage


def check_controls(policy: ExecutionPolicyV2) -> None:
    if policy.network.mode != "deny" or policy.environment.inherit:
        raise PolicyRefused("unsupported_control")
    if policy.subprocess.mode != "allow":
        raise PolicyRefused("unsupported_control")


def plan(
    inspection: Inspection,
    source: bytes,
    capability: str,
    policy: ExecutionPolicyV2,
    runtime: RuntimeImage,
    *,
    executable: bytes | None = None,
) -> ContainerPlan:
    policy = ExecutionPolicyV2.model_validate(policy.model_dump(mode="json"))
    runtime = RuntimeImage.model_validate(runtime.model_dump(mode="json"))
    check_controls(policy)
    worker = worker_plan(
        inspection,
        source,
        capability,
        ExecutionPolicy(
            limits=policy.limits, environment=policy.environment, effects=policy.effects
        ),
        executable=executable,
        check_availability=False,
    )
    return ContainerPlan(
        policy=policy,
        policy_digest=digest(policy),
        runtime=runtime,
        worker=worker,
        worker_digest=digest(worker),
    )


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
    if expected != value:
        raise ValueError("Container plan content binding mismatch")
    return value
