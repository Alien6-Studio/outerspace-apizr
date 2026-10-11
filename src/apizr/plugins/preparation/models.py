"""Bounded preparation evidence and redacted, actionable outcomes."""

import time
from dataclasses import dataclass
from threading import Event
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from apizr.capabilities.types import ValueModel
from apizr.contracts.distribution import Digest, Version, canonical_name
from apizr.plugins.artifacts.models import Manifest
from apizr.plugins.lock.models import Target

MAX_REQUIREMENTS_BYTES = 1024 * 1024
MAX_RESOLVER_BYTES = 8 * 1024 * 1024
MAX_DIAGNOSTIC_BYTES = 65536
MAX_CANDIDATES = 16384
MAX_HASHES = 512


class Model(ValueModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class Pin(Model):
    name: str = Field(max_length=128)
    version: Version

    @field_validator("name")
    @classmethod
    def canonical(cls, value: str) -> str:
        if canonical_name(value) != value:
            raise ValueError("canonical_distribution_required")
        return value


class AdmittedPin(Pin):
    hashes: tuple[Digest, ...] = Field(min_length=1, max_length=MAX_HASHES)


class Artifact(Pin):
    filename: str = Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.+!-]{0,240}\.whl$")
    sha256: Digest
    size: int = Field(gt=0, le=64 * 1024 * 1024)
    admitted_hashes: tuple[Digest, ...] = Field(min_length=1, max_length=MAX_HASHES)

    @model_validator(mode="after")
    def admitted_identity(self) -> Self:
        if self.sha256 not in self.admitted_hashes or self.admitted_hashes != tuple(
            sorted(set(self.admitted_hashes))
        ):
            raise ValueError("artifact_hash_not_admitted")
        return self


class Diagnostic(Model):
    reason: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    distribution: str | None = Field(default=None, max_length=128)
    version: Version | None = None
    target: Target | None = None
    suggested_operation: Literal["prepare"] = "prepare"


class PreparationResult(Model):
    schema_version: Literal["apizr.plugin-preparation/v1"] = (
        "apizr.plugin-preparation/v1"
    )
    state: Literal["prepared", "refused", "interrupted"]
    target: Target | None = None
    plugin: Manifest | None = None
    artifacts: tuple[Artifact, ...] = Field(default=(), max_length=128)
    requirements: Literal["requirements.lock"] | None = None
    wheelhouse: Literal["wheelhouse"] | None = None
    profile: Literal["profile"] | None = None
    resolver: str | None = Field(default=None, max_length=64)
    resolver_platform: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$"
    )
    diagnostics: tuple[Diagnostic, ...] = Field(default=(), max_length=16)
    installation: Literal["not_performed"] = "not_performed"
    activation: Literal["not_performed"] = "not_performed"

    @model_validator(mode="after")
    def complete(self) -> Self:
        if self.state == "prepared":
            if (
                self.target is None
                or self.plugin is None
                or not self.artifacts
                or self.diagnostics
                or None
                in (
                    self.requirements,
                    self.wheelhouse,
                    self.profile,
                    self.resolver,
                    self.resolver_platform,
                )
            ):
                raise ValueError("incomplete_preparation")
            names = [item.name for item in self.artifacts]
            if names != sorted(set(names)) or not any(
                (item.name, item.version) == (self.plugin.name, self.plugin.version)
                for item in self.artifacts
            ):
                raise ValueError("inconsistent_preparation")
        elif (
            not self.diagnostics
            or self.artifacts
            or self.plugin is not None
            or any(
                value is not None
                for value in (
                    self.requirements,
                    self.wheelhouse,
                    self.profile,
                    self.resolver_platform,
                )
            )
        ):
            raise ValueError("invalid_preparation_refusal")
        return self

    @property
    def exit_code(self) -> int:
        return {"prepared": 0, "refused": 2, "interrupted": 130}[self.state]


class PreparationError(Exception):
    def __init__(
        self, reason: str, distribution: str | None = None, version: str | None = None
    ) -> None:
        super().__init__(reason)
        self.diagnostic = Diagnostic(
            reason=reason, distribution=distribution, version=version
        )


@dataclass(frozen=True)
class Control:
    deadline: float
    cancel: Event | None = None

    def check(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise PreparationError("preparation_cancelled")
        if time.monotonic() >= self.deadline:
            raise PreparationError("preparation_timeout")
