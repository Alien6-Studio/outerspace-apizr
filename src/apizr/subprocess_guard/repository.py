"""Strict repository plans; no project imports occur in the transport process."""

from collections.abc import Mapping

from pydantic import JsonValue

from apizr.execution.model import ExecutionResult
from apizr.execution.policy import PolicyRefused, Subprocess
from apizr.execution.serialization import digest
from apizr.oci.model import ContainerResult, ExecutionPolicyV2, RuntimeImage
from apizr.repository_execution.docker import RepositoryDockerProvider
from apizr.repository_execution.model import (
    RepositoryContainerPlan,
    RepositoryRuntimePlan,
)
from apizr.repository_execution.planner import container_plan as allow_plan
from apizr.repository_execution.planner import evidence as evidence
from apizr.repository_execution.planner import validate_sources as validate_sources
from apizr.repository_execution.supervisor import execute as allow_execute
from apizr.repository_interfaces.model import RepositoryInterface

from .provider import DenyDockerProvider


class DenyRepositoryProvider(DenyDockerProvider, RepositoryDockerProvider):
    entrypoint = "apizr.subprocess_guard.repository_entrypoint"


def relaxed(policy: ExecutionPolicyV2) -> ExecutionPolicyV2:
    policy = ExecutionPolicyV2.model_validate(policy.model_dump(mode="json"))
    if policy.subprocess.mode != "deny" or any(
        name.startswith(("LD_", "DYLD_", "PYTHON", "GLIBC_")) or name == "GCONV_PATH"
        for name in policy.environment.allow
    ):
        raise PolicyRefused("unsupported_control")
    return policy.model_copy(update={"subprocess": Subprocess(mode="allow")})


def container_plan(
    contract: RepositoryInterface,
    exposure: bytes,
    capability: str,
    policy: ExecutionPolicyV2,
    runtime: RuntimeImage,
) -> RepositoryContainerPlan:
    value = allow_plan(contract, exposure, capability, relaxed(policy), runtime)
    return value.model_copy(update={"policy": policy, "policy_digest": digest(policy)})


def validate_plan(
    value: RepositoryRuntimePlan | RepositoryContainerPlan, exposure: bytes
) -> None:
    if not isinstance(value, RepositoryContainerPlan):
        raise ValueError("Strict OCI container plan required")
    value = RepositoryContainerPlan.model_validate(value.model_dump(mode="json"))
    expected = container_plan(
        value.worker.repository_interface,
        exposure,
        value.worker.capability_id,
        value.policy,
        value.runtime,
    )
    if value != expected:
        raise ValueError("Strict repository plan content binding mismatch")


def execute(
    plan: RepositoryRuntimePlan | RepositoryContainerPlan,
    exposure: bytes,
    sources: Mapping[str, bytes],
    payload: JsonValue,
    *,
    runtime_files: Mapping[str, bytes] | None = None,
    provider: RepositoryDockerProvider | None = None,
) -> ExecutionResult | ContainerResult:
    try:
        validate_plan(plan, exposure)
        assert isinstance(plan, RepositoryContainerPlan)
    except PolicyRefused:
        return ContainerResult(status="policy_refused")
    except (ValueError, RecursionError):
        return ContainerResult(status="binding_failed")
    selected = provider or DenyRepositoryProvider()
    if not isinstance(selected, DenyRepositoryProvider):
        return ContainerResult(status="backend_unavailable")
    policy = relaxed(plan.policy)
    inner = plan.model_copy(update={"policy": policy, "policy_digest": digest(policy)})
    return allow_execute(
        inner,
        exposure,
        sources,
        payload,
        runtime_files=runtime_files,
        provider=selected,
    )
