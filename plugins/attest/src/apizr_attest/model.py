"""Explicit identities, file references and limits; never inline credentials."""

from typing import Literal
from urllib.parse import urlsplit

from apizr_oci.model import Authentication, Docker, Model, PushRequest
from apizr_oci.oras import Transport, digest_reference
from pydantic import Field, field_validator, model_validator


class AttestError(Exception):
    """Fixed codes only. Native diagnostics can contain sensitive paths."""


class Tool(Model):
    executable: str
    version: Literal["0.1.0"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    _path = field_validator("executable")(Docker.absolute.__func__)


class Common(Model):
    expected_reference: str
    expected_signer: str = Field(pattern=r"^[0-9a-f]{64}$")
    trust_store: str
    tool: Tool
    timeout_ms: int = Field(default=120000, ge=1, le=540000)
    max_output_bytes: int = Field(default=1048576, ge=1024, le=4194304)
    _trust = field_validator("trust_store")(Docker.absolute.__func__)

    @field_validator("expected_reference")
    @classmethod
    def reference(cls, value: str) -> str:
        import re

        repository, separator, digest = value.partition("@")
        if not separator or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            raise ValueError("digest reference required")
        PushRequest.reference(repository + ":explicit")
        return value


class AttestRequest(Common):
    schema_version: Literal["apizr.attest-delivery/v1"] = Field(alias="schema")
    build_result: str
    push_result: str
    docker: Docker
    authentication: Authentication
    key_file: str
    key_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    tsa_url: str
    output_dir: str
    _paths = field_validator("build_result", "push_result", "key_file", "output_dir")(
        Docker.absolute.__func__
    )

    @field_validator("tsa_url")
    @classmethod
    def tsa(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme not in {"https", "http"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.fragment
            or url.query
            or any(c.isspace() for c in value)
        ):
            raise ValueError("explicit timestamp authority required")
        return value


class VerifyRequest(Common):
    schema_version: Literal["apizr.verify-delivery/v1"] = Field(alias="schema")
    proof_dir: str
    _proof = field_validator("proof_dir")(Docker.absolute.__func__)


class DeliveryResult(Model):
    schema_version: Literal["apizr.attest-delivery-result/v1"] = Field(
        default="apizr.attest-delivery-result/v1", alias="schema"
    )
    reference: str
    manifest_digest: str
    signer: str
    receipt_sha256: str
    checks: dict[str, Literal["pass"]]
    scope: Literal["verified OCI delivery; build not supervised by Attest"] = (
        "verified OCI delivery; build not supervised by Attest"
    )
    receipt_published: Literal[False] = False
    registry_availability_verified: Literal[False] = False


# Transport-only discovery deliberately has no Attest binary or trust inputs.


class PublishRequest(Common):
    schema_version: Literal["apizr.publish-proof/v1"] = Field(alias="schema")
    proof_dir: str
    transport: Transport
    _proof = field_validator("proof_dir")(Docker.absolute.__func__)


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


class PublishResult(Model):
    schema_version: Literal["apizr.published-proof/v1"] = Field(
        default="apizr.published-proof/v1", alias="schema"
    )
    image_reference: str
    image_digest: str
    artifact_reference: str | None = None
    artifact_manifest_digest: str | None = None
    receipt_sha256: str
    verification: DeliveryResult
    state: Literal["verified", "remote_state_unconfirmed"] = "verified"
    receipt_published: bool = True

    @model_validator(mode="after")
    def confirmation(self):
        if self.state == "verified":
            if (
                not self.receipt_published
                or self.artifact_reference is None
                or self.artifact_manifest_digest is None
            ):
                raise ValueError("verified publication requires artifact identities")
        elif (
            self.receipt_published
            or self.artifact_reference is not None
            or self.artifact_manifest_digest is not None
        ):
            raise ValueError("unconfirmed publication cannot claim remote identities")
        return self


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
