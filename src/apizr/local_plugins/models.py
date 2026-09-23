"""Declarative local installation records, independent of CLI and execution."""

import re
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, field_validator

from apizr.capabilities.types import ValueModel, logical_module

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Version = Annotated[str, Field(pattern=r"^[0-9][A-Za-z0-9.!+_]{0,127}$")]


class PluginError(Exception):
    """Stable failures without installer logs, paths or environment values."""


def canonical_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?", value):
        raise ValueError("Invalid distribution name")
    return re.sub(r"[-_.]+", "-", value).lower()


class Manifest(ValueModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["apizr.extension-manifest/v1"] = Field(alias="schema")
    name: str
    version: Version
    module: str
    protocol: Literal["apizr.extension/v1"]

    @field_validator("name")
    @classmethod
    def name_is_canonical(cls, value: str) -> str:
        if canonical_name(value) != value:
            raise ValueError("Manifest name must be canonical")
        return value

    @field_validator("module")
    @classmethod
    def module_is_canonical(cls, value: str) -> str:
        if len(value) > 256 or logical_module(value) != value:
            raise ValueError("Invalid module")
        return value


class LockedDistribution(ValueModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    name: str
    version: Version
    sha256: Digest

    @field_validator("name")
    @classmethod
    def canonical_distribution(cls, value: str) -> str:
        if canonical_name(value) != value:
            raise ValueError("Distribution name must be canonical")
        return value


class Installation(Manifest):
    sha256: Digest
    environment_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    python: str
    lock_sha256: Digest | None = None
    dependencies: list[LockedDistribution] = Field(
        default_factory=list[LockedDistribution], max_length=127
    )


class Inventory(ValueModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["apizr.installed-extensions/v1"] = Field(
        default="apizr.installed-extensions/v1", alias="schema"
    )
    installations: list[Installation] = Field(
        default_factory=list[Installation], max_length=1000
    )
