"""Explicit identities, file references and limits; never inline credentials."""

from typing import Literal
from urllib.parse import urlsplit

from apizr_oci.model import Authentication, Docker, Model, PushRequest
from pydantic import Field, field_validator


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
