"""Bind invocation/effects to already validated repository evidence, without analysis."""

import json
from collections.abc import Mapping
from typing import Any, Literal

from apizr.capabilities.model import Digest, Effects
from apizr.execution.policy import (
    BackendCapabilities,
    ExecutionPolicy,
    PolicyRefused,
    check_controls,
)
from apizr.execution.serialization import digest
from apizr.interfaces.serialization import json_bytes
from apizr.oci.model import ExecutionPolicyV2, RuntimeImage
from apizr.oci.planner import check_controls as check_oci_controls
from apizr.repository_interfaces.model import RepositoryInterface

from .model import RepositoryContainerPlan, RepositoryRuntimePlan


def evidence(
    contract: RepositoryInterface, exposure: bytes, backend: str
) -> dict[str, Any]:
    if Digest.of_bytes(exposure) != contract.exposure_plan_digest:
        raise ValueError("Exposure identity mismatch")
    document: dict[str, Any] = json.loads(exposure)
    if (
        document["schema_version"] != "apizr.exposure-plan/v1"
        or contract.interface not in document["interfaces"]
    ):
        raise ValueError("Exposure contract mismatch")
    for field in (
        "repository_digest",
        "catalog_digest",
        "graph_digest",
        "repository_readiness_digest",
    ):
        if document[field] != getattr(contract, field).model_dump(mode="json"):
            raise ValueError("Repository evidence mismatch")
    records = document["capabilities"]
    if [c["capability_id"] for c in records] != [
        c.capability_id for c in contract.capabilities
    ]:
        raise ValueError("Selected identities mismatch")
    if any(
        backend not in c["compatible_execution_modes"]
        or contract.interface not in c["compatible_interfaces"]
        for c in records
    ):
        raise PolicyRefused("repository_backend_incompatible")
    return {c["capability_id"]: c for c in records}


def worker_plan(
    contract: RepositoryInterface,
    exposure: bytes,
    capability: str,
    policy: ExecutionPolicy,
    *,
    context: Literal["local-process", "oci-container"] = "local-process",
) -> RepositoryRuntimePlan:
    contract = RepositoryInterface.model_validate(contract.model_dump(mode="json"))
    policy = ExecutionPolicy.model_validate(policy.model_dump(mode="json"))
    check_controls(policy, BackendCapabilities(available=True))
    records = evidence(contract, exposure, context)
    selected = next(
        (c for c in contract.capabilities if c.capability_id == capability), None
    )
    if selected is None:
        raise ValueError("Capability is not exposed")
    record = records[capability]
    if record["module"] != selected.module or record["source_path"] != next(
        s.source_path for s in contract.sources if s.module == selected.module
    ):
        raise ValueError("Exposure source mismatch")
    effects = Effects.model_validate(record["effects"])
    for name in policy.effects.require_known:
        if effects.model_dump(mode="json")[name]["value"] == "unknown":
            raise PolicyRefused("unknown_required_effect")
    return RepositoryRuntimePlan(
        execution_context=context,
        repository_interface=contract,
        repository_interface_digest=digest(contract),
        exposure_plan_digest=contract.exposure_plan_digest,
        source_universe_digest=Digest.of_bytes(
            json_bytes([s.model_dump(mode="json") for s in contract.sources])
        ),
        capability_id=capability,
        interface=selected.invocation,
        interface_digest=digest(selected.invocation),
        effects=effects,
        policy=policy,
        policy_digest=digest(policy),
    )


def container_plan(
    contract: RepositoryInterface,
    exposure: bytes,
    capability: str,
    policy: ExecutionPolicyV2,
    runtime: RuntimeImage,
) -> RepositoryContainerPlan:
    policy = ExecutionPolicyV2.model_validate(policy.model_dump(mode="json"))
    runtime = RuntimeImage.model_validate(runtime.model_dump(mode="json"))
    check_oci_controls(policy)
    worker = worker_plan(
        contract,
        exposure,
        capability,
        ExecutionPolicy(
            limits=policy.limits, environment=policy.environment, effects=policy.effects
        ),
        context="oci-container",
    )
    return RepositoryContainerPlan(
        policy=policy,
        policy_digest=digest(policy),
        runtime=runtime,
        worker=worker,
        worker_digest=digest(worker),
    )


def validate_plan(
    plan: RepositoryRuntimePlan | RepositoryContainerPlan, exposure: bytes
) -> None:
    if isinstance(plan, RepositoryContainerPlan):
        parsed = RepositoryContainerPlan.model_validate(plan.model_dump(mode="json"))
        expected = container_plan(
            parsed.worker.repository_interface,
            exposure,
            parsed.worker.capability_id,
            parsed.policy,
            parsed.runtime,
        )
    else:
        parsed = RepositoryRuntimePlan.model_validate(plan.model_dump(mode="json"))
        expected = worker_plan(
            parsed.repository_interface,
            exposure,
            parsed.capability_id,
            parsed.policy,
            context=parsed.execution_context,
        )
    if parsed != expected:
        raise ValueError("Repository runtime binding mismatch")


def validate_sources(
    contract: RepositoryInterface, sources: Mapping[str, bytes]
) -> None:
    if set(sources) != {s.bundle_path for s in contract.sources}:
        raise ValueError("Repository source universe mismatch")
    for source in contract.sources:
        content: object = sources[source.bundle_path]
        if not content_matches(content, source.size, source.source_digest):
            raise ValueError("Repository source content mismatch")


def content_matches(content: object, size: int, expected: Digest) -> bool:
    return (
        isinstance(content, bytes)
        and len(content) == size
        and Digest.of_bytes(content) == expected
    )
