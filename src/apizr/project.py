"""Explicit, bounded project-file loading for repository compiler operations."""

import json
import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from apizr.capabilities.types import ValueModel
from apizr.config_files import read_regular
from apizr.graph import GraphPolicy
from apizr.local_plugins.models import LockedDistribution
from apizr.repository import ScanPolicy

MAX_PROJECT_BYTES = 65536


class PluginDeclaration(LockedDistribution):
    """Artifact identity only: no installation or execution authority."""

    requirements: str | None = None

    @field_validator("version")
    @classmethod
    def exact_version(cls, value: str) -> str:
        if not re.fullmatch(
            r"(?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?"
            r"(?:\.post[0-9]+)?(?:\.dev[0-9]+)?(?:\+[a-z0-9]+(?:[._-][a-z0-9]+)*)?",
            value,
        ):
            raise ValueError("Expected an exact normalized version")
        return value

    @field_validator("requirements")
    @classmethod
    def portable_requirements(cls, value: str | None) -> str | None:
        if value is not None and (
            not value
            or len(value) > 256
            or "\\" in value
            or ":" in value
            or "\0" in value
            or Path(value).is_absolute()
            or any(part in ("", ".", "..") for part in value.split("/"))
        ):
            raise ValueError("Requirements must be a portable project-relative path")
        return value


class ProjectConfig(ValueModel):
    """Project locations and existing analysis settings, not a policy language.

    ``load_project`` resolves file paths and adds the standard scan exclusions.
    Source roots retain ScanPolicy's meaning: relative to the repository root.
    """

    schema_version: Literal["apizr.project/v1"]
    root: Path = Path(".")
    plugins: tuple[PluginDeclaration, ...] = Field(default=(), max_length=32)

    @field_validator("plugins")
    @classmethod
    def unique_plugins(
        cls, value: tuple[PluginDeclaration, ...]
    ) -> tuple[PluginDeclaration, ...]:
        if len({item.name for item in value}) != len(value):
            raise ValueError("Duplicate plugin declaration")
        return value

    scan: ScanPolicy = Field(default_factory=ScanPolicy)
    graph: GraphPolicy = Field(default_factory=GraphPolicy)
    readiness_policy: Path | None = None
    exposure_policy: Path | None = None

    @field_validator("root", "readiness_policy", "exposure_policy", mode="before")
    @classmethod
    def local_paths(cls, value: object) -> object:
        if isinstance(value, str) and (
            not value or "\0" in value or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value)
        ):
            raise ValueError("Expected a nonempty local path, not a URI")
        return value


def load_project(path: str | Path) -> ProjectConfig:
    """Load only the named TOML file, capped at 64 KiB, with strict validation.

    Root/policy paths are relative to the named file's directory, never CWD.
    No policy files, project code, environment variables or plugins are loaded.
    The caller may override a policy path before reading the chosen JSON file.
    """
    path = Path(path).absolute()
    try:
        raw = read_regular(path, MAX_PROJECT_BYTES)
    except ValueError as error:
        if str(error) == "file_too_large":
            raise ValueError("Project file exceeds size limit") from None
        raise
    document = tomllib.loads(raw.decode("utf-8"))
    try:
        # Strict JSON validation accepts TOML arrays for existing tuple fields,
        # while refusing coercion of strings, floats or booleans to integers.
        serialized = json.dumps(document)
    except TypeError as error:
        raise ValueError(
            "Project settings cannot contain TOML date/time values"
        ) from error
    config = ProjectConfig.model_validate_json(serialized, strict=True)
    scan = ScanPolicy.model_validate(
        {
            **config.scan.model_dump(),
            "excluded_directories": (
                *ScanPolicy().excluded_directories,
                *config.scan.excluded_directories,
            ),
        }
    )
    return config.model_copy(
        update={
            "root": path.parent / config.root,
            "readiness_policy": path.parent / config.readiness_policy
            if config.readiness_policy is not None
            else None,
            "exposure_policy": path.parent / config.exposure_policy
            if config.exposure_policy is not None
            else None,
            "scan": scan,
        }
    )
