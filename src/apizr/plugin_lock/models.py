"""Portable artifact contracts, deliberately separate from installation records."""

import platform
import sys
import sysconfig
from typing import Literal

from pydantic import Field, field_validator

from apizr.capabilities.types import ValueModel
from apizr.local_plugins.models import Digest, LockedDistribution, Manifest
from apizr.project import PluginDeclaration


class Target(ValueModel):
    implementation: str = Field(max_length=64)
    python: str = Field(pattern=r"^3\.[0-9]+\.[0-9]+$")
    platform: str = Field(max_length=128)
    machine: str = Field(max_length=64)
    abi: str = Field(max_length=128)


def current_target() -> Target:
    return Target(
        implementation=sys.implementation.name,
        python=platform.python_version(),
        platform=sysconfig.get_platform(),
        machine=platform.machine(),
        abi=str(sysconfig.get_config_var("SOABI") or ""),
    )


class Wheel(LockedDistribution):
    filename: str = Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.+!-]{0,240}\.whl$")


class Requirements(ValueModel):
    path: str
    source_sha256: Digest

    @field_validator("path")
    @classmethod
    def portable_path(cls, value: str) -> str:
        PluginDeclaration.portable_requirements(value)
        return value


class Plugin(ValueModel):
    manifest: Manifest
    wheel: Wheel
    dependencies: tuple[Wheel, ...] = Field(default=(), max_length=127)
    requirements: Requirements | None = None


class ProjectLock(ValueModel):
    schema_version: Literal["apizr.project-plugins/v1"] = "apizr.project-plugins/v1"
    target: Target
    plugins: tuple[Plugin, ...] = Field(max_length=32)


class Diagnostic(ValueModel):
    code: str
    plugin: str | None = None
    distribution: str | None = None


class InstalledState(ValueModel):
    name: str
    matches: bool
    active: bool


class Result(ValueModel):
    schema_version: Literal["apizr.plugin-lock-result/v1"] = (
        "apizr.plugin-lock-result/v1"
    )
    valid: bool
    lock_sha256: Digest | None = None
    target: Target | None = None
    diagnostics: tuple[Diagnostic, ...] = ()
    installed: tuple[InstalledState, ...] = ()


class LockError(Exception):
    """Redacted input/read failure (CLI 2), distinct from a content mismatch (1)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
