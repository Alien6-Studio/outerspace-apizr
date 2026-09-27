"""Pure source identities; acquisition and analysis grant different effects."""

import os
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from apizr.git_source.contracts import (
    is_ssh,
    relative_path,
    validate_ref,
    validate_ssh_url,
    validate_url,
)
from apizr.publication_contracts import Model


class LocalTarget(Model):
    kind: Literal["local"] = "local"
    root: str

    @field_validator("root")
    @classmethod
    def absolute_root(cls, value: str) -> str:
        if (
            not value.startswith("/")
            or value.startswith("//")
            or "\0" in value
            or value != os.path.normpath(value)
        ):
            raise ValueError("canonical absolute root required")
        return value


class GitAnalysisTarget(Model):
    kind: Literal["git"] = "git"
    repository: str
    reference: str
    subdir: str = "."

    @model_validator(mode="after")
    def validate_source(self) -> "GitAnalysisTarget":
        (validate_ssh_url if is_ssh(self.repository) else validate_url)(self.repository)
        validate_ref(self.reference)
        relative_path(self.subdir)
        return self


AnalysisTarget = Annotated[LocalTarget | GitAnalysisTarget, Field(discriminator="kind")]


class PinnedRoot(LocalTarget):
    """An additional inode restriction; it never replaces operator authorization."""

    device: int = Field(ge=0)
    inode: int = Field(ge=0)
