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
