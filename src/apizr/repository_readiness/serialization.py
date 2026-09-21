"""Independent canonical policy/report identities; no source identity introduced."""

from typing import TYPE_CHECKING

from apizr.capabilities.model import Digest
from apizr.repository.serialization import canonical_bytes

from .policy import RepositoryReadinessPolicy

if TYPE_CHECKING:
    from .model import RepositoryReadinessReport


def policy_bytes(policy: RepositoryReadinessPolicy) -> bytes:
    return canonical_bytes(
        RepositoryReadinessPolicy.model_validate(policy.model_dump(mode="json"))
    )


def policy_digest(policy: RepositoryReadinessPolicy) -> Digest:
    return Digest.of_bytes(policy_bytes(policy))


def report_bytes(report: "RepositoryReadinessReport") -> bytes:
    from .model import RepositoryReadinessReport

    return canonical_bytes(
        RepositoryReadinessReport.model_validate(report.model_dump(mode="json"))
    )


def report_digest(report: "RepositoryReadinessReport") -> Digest:
    return Digest.of_bytes(report_bytes(report))
