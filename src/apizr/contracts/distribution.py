"""Shared pure distribution identities used by plugin locks and delivery plans."""

import re
from typing import Annotated

from pydantic import ConfigDict, Field, field_validator

from apizr.capabilities.types import ValueModel

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Version = Annotated[str, Field(pattern=r"^[0-9][A-Za-z0-9.!+_]{0,127}$")]


def canonical_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?", value):
        raise ValueError("Invalid distribution name")
    return re.sub(r"[-_.]+", "-", value).lower()


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
