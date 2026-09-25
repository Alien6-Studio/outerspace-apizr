"""Explicit, bounded inputs. No Docker command, shell or inherited credentials."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BuildError(Exception):
    """Fixed diagnostic codes only; never expose Docker logs or argument values."""


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
