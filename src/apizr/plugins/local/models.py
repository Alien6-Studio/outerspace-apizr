"""Declarative local installation records, independent of CLI and execution."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from apizr.capabilities.types import ValueModel
from apizr.plugins.artifacts.models import (
    Digest as Digest,
)
from apizr.plugins.artifacts.models import (
    LockedDistribution as LockedDistribution,
)
from apizr.plugins.artifacts.models import Manifest as Manifest
from apizr.plugins.artifacts.models import PluginError as PluginError
from apizr.plugins.artifacts.models import (
    Version as Version,
)
from apizr.plugins.artifacts.models import (
    canonical_name as canonical_name,
)


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
