"""Canonical JSON identities independent of filesystem location and selector order."""

from apizr.capabilities.model import Digest
from apizr.repository.serialization import canonical_bytes

from .model import ExposurePlan
from .policy import ExposurePolicy


def policy_bytes(policy: ExposurePolicy) -> bytes:
    return canonical_bytes(
        ExposurePolicy.model_validate(policy.model_dump(mode="json"))
    )


def policy_digest(policy: ExposurePolicy) -> Digest:
    return Digest.of_bytes(policy_bytes(policy))


def plan_bytes(plan: ExposurePlan) -> bytes:
    return canonical_bytes(ExposurePlan.model_validate(plan.model_dump(mode="json")))


def plan_digest(plan: ExposurePlan) -> Digest:
    return Digest.of_bytes(plan_bytes(plan))
