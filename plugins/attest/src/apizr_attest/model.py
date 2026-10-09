"""Explicit identities, file references and limits; never inline credentials."""

from typing import Literal

from apizr_oci.model import Docker, Model
from pydantic import Field, field_validator

from apizr.contracts.publication import (
    AdmitRequest as AdmitRequest,
)
from apizr.contracts.publication import (
    AttestRequest as AttestRequest,
)
from apizr.contracts.publication import (
    Common as Common,
)
from apizr.contracts.publication import (
    PublishRequest as PublishRequest,
)
from apizr.contracts.publication import (
    Tool as Tool,
)
from apizr.contracts.publication import Transport, digest_reference
from apizr.contracts.publication import (
    VerifyRequest as VerifyRequest,
)
from apizr.contracts.results import (
    AdmissionResult as AdmissionResult,
)
from apizr.contracts.results import (
    DeliveryResult as DeliveryResult,
)
from apizr.contracts.results import (
    PublishResult as PublishResult,
)
from apizr.contracts.results import (
    VerifiedAttestTool as VerifiedAttestTool,
)


class AttestError(Exception):
    """Fixed codes only. Native diagnostics can contain sensitive paths."""


class DiscoverRequest(Model):
    schema_version: Literal["apizr.discover-proofs/v1"] = Field(alias="schema")
    expected_reference: str
    transport: Transport
    timeout_ms: int = Field(default=120000, ge=1, le=540000)
    _reference = field_validator("expected_reference")(lambda v: digest_reference(v))


class FetchRequest(Common):
    schema_version: Literal["apizr.fetch-proof/v1"] = Field(alias="schema")
    artifact_reference: str
    output_dir: str
    transport: Transport
    _artifact = field_validator("artifact_reference")(lambda v: digest_reference(v))
    _output = field_validator("output_dir")(Docker.absolute.__func__)


class Candidate(Model):
    reference: str
    digest: str
    mediaType: str
    size: int
    artifact_type: str
    verified: Literal[False] = False


class DiscoverResult(Model):
    schema_version: Literal["apizr.discovered-proofs/v1"] = Field(
        default="apizr.discovered-proofs/v1", alias="schema"
    )
    image_reference: str
    candidates: list[Candidate]
    complete: Literal[True] = True


class FetchResult(Model):
    schema_version: Literal["apizr.fetched-proof/v1"] = Field(
        default="apizr.fetched-proof/v1", alias="schema"
    )
    image_reference: str
    image_digest: str
    artifact_reference: str
    artifact_manifest_digest: str
    receipt_sha256: str
    verification: DeliveryResult
