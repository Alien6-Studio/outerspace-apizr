"""Explicit, bounded inputs. No Docker command, shell or inherited credentials."""

from typing import Literal

from pydantic import Field, field_validator

from apizr.publication_contracts import (
    Authentication as Authentication,
)
from apizr.publication_contracts import (
    Docker as Docker,
)
from apizr.publication_contracts import (
    Model as Model,
)
from apizr.publication_contracts import (
    PushRequest as PushRequest,
)


class BuildError(Exception):
    """Fixed diagnostic codes only; never expose Docker logs or argument values."""


class BuildRequest(Model):
    schema_version: Literal["apizr.oci-build/v1"] = Field(alias="schema")
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
    timeout_ms: int = Field(default=300000, ge=1, le=540000)
    max_log_bytes: int = Field(default=1048576, ge=1024, le=16777216)

    _paths = field_validator("bundle", "requirements", "wheelhouse")(
        Docker.absolute.__func__
    )


class BuildResult(Model):
    schema_version: Literal["apizr.oci-build-result/v1"] = Field(
        default="apizr.oci-build-result/v1", alias="schema"
    )
    tag: str
    platform: str
    image_id: str
    inputs_sha256: str
    published: Literal[False] = False


class PushResult(Model):
    schema_version: Literal["apizr.oci-push-result/v1"] = Field(
        default="apizr.oci-push-result/v1", alias="schema"
    )
    destination: str
    digest_reference: str
    platform: str
    image_id: str
    config_digest: str
    manifest_digest: str
    index_digest: None = None
    inputs_sha256: str
    published: Literal[True] = True
