"""A catalog describes artifacts, never installation or execution authority."""

from typing import Literal, Self

from pydantic import Field, model_validator

from apizr.capabilities.types import ValueModel
from apizr.local_plugins.models import Manifest, Version
from apizr.plugin_lock.models import Requirements, Target, Wheel
from apizr.project import PluginDeclaration


class Identity(ValueModel):
    name: str
    version: Version

    @model_validator(mode="after")
    def exact(self) -> Self:
        PluginDeclaration(name=self.name, version=self.version, sha256="0" * 64)
        return self


class Artifact(Wheel):
    size: int = Field(gt=0, le=64 * 1024 * 1024)


class Compatibility(ValueModel):
    apizr_version: Version
    channel: Literal["development", "published"]
    target: Target


class Provenance(ValueModel):
    repository: str = Field(pattern=r"^https://[^\s?#]+$", max_length=512)
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    status: Literal["development", "published"]
    publication: str | None = Field(default=None, max_length=1024)


class Prerequisite(ValueModel):
    tool: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9 /.-]{0,63}$")
    operations: tuple[str, ...] = Field(min_length=1, max_length=32)


class Entry(ValueModel):
    description: str = Field(min_length=1, max_length=2048)
    manifest: Manifest
    wheel: Artifact
    dependencies: tuple[Artifact, ...] = Field(default=(), max_length=127)
    requirements: Requirements | None = None
    compatibility: Compatibility
    prerequisites: tuple[Prerequisite, ...] = Field(default=(), max_length=16)
    provenance: Provenance

    @model_validator(mode="after")
    def consistent(self) -> Self:
        Identity(name=self.manifest.name, version=self.manifest.version)
        if (self.wheel.name, self.wheel.version) != (
            self.manifest.name,
            self.manifest.version,
        ):
            raise ValueError("inconsistent_identity")
        names = [self.wheel.name, *(w.name for w in self.dependencies)]
        if len(names) != len(set(names)) or (
            self.dependencies and not self.requirements
        ):
            raise ValueError("invalid_closure")
        if self.compatibility.channel != self.provenance.status:
            raise ValueError("inconsistent_channel")
        if (
            self.requirements
            and self.requirements.path != f"requirements/{self.wheel.name}.lock"
        ):
            raise ValueError("noncanonical_requirements_path")
        return self


class Profile(ValueModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    plugins: tuple[Identity, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({p.name for p in self.plugins}) != len(self.plugins):
            raise ValueError("duplicate_profile_plugin")
        return self


class Catalog(ValueModel):
    schema_version: Literal["apizr.plugin-catalog/v1"] = "apizr.plugin-catalog/v1"
    entries: tuple[Entry, ...] = Field(min_length=1, max_length=128)
    profiles: tuple[Profile, ...] = Field(max_length=32)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        keys = [
            (
                e.wheel.name,
                e.wheel.version,
                e.wheel.sha256,
                e.compatibility.target.model_dump_json(),
            )
            for e in self.entries
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate_entry")
        if len({p.name for p in self.profiles}) != len(self.profiles):
            raise ValueError("duplicate_profile")
        identities = {(e.wheel.name, e.wheel.version) for e in self.entries}
        if any(
            (p.name, p.version) not in identities
            for profile in self.profiles
            for p in profile.plugins
        ):
            raise ValueError("missing_profile_entry")
        return self


class CatalogError(Exception):
    """Stable diagnostic without input contents, paths or external tool output."""


class Resolution(ValueModel):
    schema_version: Literal["apizr.plugin-catalog-result/v1"] = (
        "apizr.plugin-catalog-result/v1"
    )
    profile: str
    target: Target
    plugins: tuple[Identity, ...]
    files: tuple[str, ...]
    compatibility: Literal["declared"] = "declared"
    artifacts: Literal["statically_verified"] = "statically_verified"
    installation: Literal["not_performed"] = "not_performed"
