"""Plugin manifest identity and shared redacted artifact failures."""

from typing import Literal

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
