"""Shared build, signing and publication input contracts: validation only, no tools or file reads.

The core and optional plugins use these same models before any operational I/O.
"""

import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apizr.delivery import (
    DeliveryManifest,
    DeliveryPlan,
    ProofRequirement,
    check_observation,
    identity,
)

DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Docker(Model):
    executable: str
    socket: str
    buildx: str | None = None

    @field_validator("executable", "socket")
    @classmethod
    def absolute(cls, value: str) -> str:
        if not Path(value).is_absolute() or any(c in value for c in "\0\r\n"):
            raise ValueError("absolute path required")
        return value

    @field_validator("buildx")
    @classmethod
    def buildx_path(cls, value: str | None) -> str | None:
        return cls.absolute(value) if value is not None else None


class Authentication(Model):
    """An explicit Docker auths file; credential helpers are not executed."""

    config_file: str
    ca_file: str | None = None

    _config = field_validator("config_file")(Docker.absolute.__func__)

    @field_validator("ca_file")
    @classmethod
    def optional_ca(cls, value: str | None) -> str | None:
        return Docker.absolute(value) if value is not None else None


class PushRequest(Model):
    delivery_plan: DeliveryPlan | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    delivery_manifest: DeliveryManifest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def delivery_binding(self):
        if self.delivery_plan is not None and (
            self.delivery_manifest is None
            or identity(self.delivery_plan)
            != self.delivery_manifest.delivery_plan_digest
            or self.delivery_plan.platform != self.platform
        ):
            raise ValueError("Delivery plan and manifest disagree")
        if self.delivery_manifest is not None:
            check_observation(
                self.delivery_manifest, self.image_id, self.platform, self.inputs_sha256
            )
        return self

    schema_version: Literal["apizr.oci-push/v1"] = Field(alias="schema")
    image_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    platform: Literal["linux/amd64", "linux/arm64"]
    inputs_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    destination: str = Field(max_length=255)
    docker: Docker
    authentication: Authentication
    timeout_ms: int = Field(default=300000, ge=1, le=540000)
    max_log_bytes: int = Field(default=1048576, ge=1024, le=16777216)

    @field_validator("destination")
    @classmethod
    def reference(cls, value: str) -> str:
        import ipaddress
        import re

        host = r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
        part = r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
        if (
            re.fullmatch(
                rf"{host}(?::[1-9][0-9]{{0,4}})?/{part}(?:/{part})+:[A-Za-z0-9_][A-Za-z0-9_.-]{{0,127}}",
                value,
            )
            is None
        ):
            raise ValueError("explicit registry/namespace/image:tag required")
        registry = value.split("/", 1)[0]
        try:
            ipaddress.ip_address(registry.split(":", 1)[0])
        except ValueError:
            pass
        else:
            raise ValueError("DNS registry name required")
        if ":" in registry and int(registry.rsplit(":", 1)[1]) > 65535:
            raise ValueError("invalid registry port")
        return value


def digest_reference(value: str) -> str:
    repository, separator, digest = value.partition("@")
    if len(value) > 320 or not separator or DIGEST.fullmatch(digest) is None:
        raise ValueError("explicit digest reference required")
    PushRequest.reference(repository + ":explicit")
    return value


class OrasTool(Model):
    executable: str
    version: Literal["1.3.4"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    _path = field_validator("executable")(Docker.absolute.__func__)


class Transport(Model):
    tool: OrasTool
    authentication: Authentication
    max_candidates: int = Field(default=128, ge=1, le=128)
    max_discovery_bytes: int = Field(default=1048576, ge=1024, le=4194304)


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


class PublishRequest(Common):
    schema_version: Literal["apizr.publish-proof/v1"] = Field(alias="schema")
    proof_dir: str
    transport: Transport
    _proof = field_validator("proof_dir")(Docker.absolute.__func__)


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


class BuildTarget(Model):
    """Exact references and tool parameters shared by build inputs and grants."""

    proof_requirement: ProofRequirement = "optional"
    bundle: str
    interface: Literal["rest", "mcp"]
    base_image: str = Field(
        pattern=r"^[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}$", max_length=512
    )
    platform: Literal["linux/amd64", "linux/arm64"]
    tag: str = Field(
        pattern=r"^[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9_][A-Za-z0-9_.-]*$", max_length=200
    )
    requirements: str
    wheelhouse: str
    docker: Docker

    _paths = field_validator("bundle", "requirements", "wheelhouse")(
        Docker.absolute.__func__
    )


class BuildRequest(BuildTarget):
    schema_version: Literal["apizr.oci-build/v1"] = Field(alias="schema")
    timeout_ms: int = Field(default=300000, ge=1, le=540000)
    max_log_bytes: int = Field(default=1048576, ge=1024, le=16777216)


class AdmitRequest(Common):
    schema_version: Literal["apizr.admit-delivery/v1"] = Field(alias="schema")
    push_result: str
    delivery_manifest: DeliveryManifest
    destination: str
    artifact_reference: str
    transport: Transport
    docker: Docker
    _push = field_validator("push_result")(Docker.absolute.__func__)
    _destination = field_validator("destination")(PushRequest.reference.__func__)

    @field_validator("artifact_reference")
    @classmethod
    def artifact(cls, value: str) -> str:
        return digest_reference(value)

    @model_validator(mode="after")
    def same_repository(self):
        if {
            self.destination.rsplit(":", 1)[0],
            self.expected_reference.split("@")[0],
            self.artifact_reference.split("@")[0],
        } != {self.destination.rsplit(":", 1)[0]}:
            raise ValueError("Admission requires one exact repository")
        return self
