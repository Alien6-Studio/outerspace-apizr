"""Declared controls are requirements, never a claim of sandboxing."""

import os
import re
from typing import Literal, Self

from pydantic import Field, StrictBool, field_validator, model_validator

from apizr.capabilities.types import ValueModel

EffectName = Literal[
    "filesystem_read",
    "filesystem_write",
    "network",
    "environment",
    "subprocess",
    "state_mutation",
    "secrets",
    "external_service",
]
Control = Literal[
    "wall_timeout",
    "input_limit",
    "output_limit",
    "environment",
    "working_directory",
    "network_deny",
    "filesystem_sandbox",
    "subprocess_deny",
]


class Limits(ValueModel):
    wall_time_ms: int = Field(default=5000, strict=True, ge=1, le=3600000)
    max_input_bytes: int = Field(default=1048576, strict=True, ge=1, le=16777216)
    max_output_bytes: int = Field(default=1048576, strict=True, ge=128, le=16777216)


class Environment(ValueModel):
    inherit: StrictBool = False
    allow: tuple[str, ...] = ()

    @field_validator("allow")
    @classmethod
    def names(cls, names: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in names):
            raise ValueError("Expected environment variable names")
        return tuple(sorted(set(names)))

    @model_validator(mode="after")
    def unambiguous(self) -> Self:
        if self.inherit and self.allow:
            raise ValueError("Allowlist applies only to a clean environment")
        return self


class Network(ValueModel):
    mode: Literal["inherit", "deny"] = "inherit"


class Filesystem(ValueModel):
    mode: Literal["host", "sandbox"] = "host"


class Subprocess(ValueModel):
    mode: Literal["allow", "deny"] = "allow"


class Effects(ValueModel):
    require_known: tuple[EffectName, ...] = ()

    @field_validator("require_known")
    @classmethod
    def ordered(cls, value: tuple[EffectName, ...]) -> tuple[EffectName, ...]:
        return tuple(sorted(set(value)))


class ExecutionPolicy(ValueModel):
    schema_version: Literal["apizr.execution/v1"] = "apizr.execution/v1"
    backend: Literal["local-process"] = "local-process"
    limits: Limits = Limits()
    environment: Environment = Environment()
    network: Network = Network()
    filesystem: Filesystem = Filesystem()
    subprocess: Subprocess = Subprocess()
    effects: Effects = Effects()
    working_directory: Literal["fresh"] = "fresh"


class BackendCapabilities(ValueModel):
    schema_version: Literal["apizr.backend/v1"] = "apizr.backend/v1"
    backend_version: Literal["apizr.local-process/v1"] = "apizr.local-process/v1"
    available: bool
    enforced: tuple[Control, ...] = (
        "wall_timeout",
        "input_limit",
        "output_limit",
        "environment",
        "working_directory",
    )
    unsupported: tuple[Control, ...] = (
        "network_deny",
        "filesystem_sandbox",
        "subprocess_deny",
    )


def local_capabilities() -> BackendCapabilities:
    # Pipe selectors + session/process-group cleanup require POSIX in this backend.
    return BackendCapabilities(available=os.name == "posix")


class PolicyRefused(ValueError):
    """Stable, value-free policy refusal; no environment or source diagnostics."""


def check_controls(policy: ExecutionPolicy, backend: BackendCapabilities) -> None:
    requested: set[Control] = {
        "wall_timeout",
        "input_limit",
        "output_limit",
        "environment",
        "working_directory",
    }
    if policy.network.mode == "deny":
        requested.add("network_deny")
    if policy.filesystem.mode == "sandbox":
        requested.add("filesystem_sandbox")
    if policy.subprocess.mode == "deny":
        requested.add("subprocess_deny")
    if not backend.available:
        raise PolicyRefused("backend_unavailable")
    if requested - set(backend.enforced):
        raise PolicyRefused("unsupported_control")
