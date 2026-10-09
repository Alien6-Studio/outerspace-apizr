"""Declarative local installation records, independent of CLI and execution."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, field_validator

from apizr.capabilities.types import ValueModel, logical_module
from apizr.contracts.distribution import (
    Digest as Digest,
)
from apizr.contracts.distribution import (
    LockedDistribution as LockedDistribution,
)
from apizr.contracts.distribution import (
    Version as Version,
)
from apizr.contracts.distribution import (
    canonical_name as canonical_name,
)


class PluginError(Exception):
    """Stable failures without installer logs, paths or environment values."""


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
