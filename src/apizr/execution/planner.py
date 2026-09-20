"""Compare execution requirements with the backend, independently of readiness."""

from apizr.capabilities.model import EffectValue
from apizr.inspection import Inspection
from apizr.interfaces.planner import plan as interface_plan

from .model import RuntimePlan
from .policy import ExecutionPolicy, PolicyRefused, check_controls, local_capabilities
from .serialization import digest


def plan(
    inspection: Inspection,
    source: bytes,
    capability: str,
    policy: ExecutionPolicy,
    *,
    executable: bytes | None = None,
) -> RuntimePlan:
    policy = ExecutionPolicy.model_validate(policy.model_dump(mode="json"))
    check_controls(policy, local_capabilities())
    shared = interface_plan(
        inspection, source, executable=executable, select=[capability]
    )
    invocation = shared.capabilities[0]
    effects = next(
        c.effects
        for c in inspection.capability_ir.capabilities
        if c.id == invocation.capability_id
    )
    for name in policy.effects.require_known:
        if effects.model_dump()[name]["value"] == EffectValue.UNKNOWN:
            raise PolicyRefused("unknown_required_effect")
    return RuntimePlan(
        **shared.model_dump(exclude={"capabilities"}),
        capability_id=invocation.capability_id,
        interface=invocation,
        interface_digest=digest(invocation),
        policy=policy,
        policy_digest=digest(policy),
        inspection=inspection,
    )


def validate_plan(
    runtime: RuntimePlan, source: bytes, executable: bytes
) -> RuntimePlan:
    validated = RuntimePlan.model_validate(runtime.model_dump(mode="json"))
    expected = plan(
        validated.inspection,
        source,
        validated.capability_id,
        validated.policy,
        executable=executable,
    )
    if expected != validated:
        raise ValueError("Runtime plan content binding mismatch")
    return validated
