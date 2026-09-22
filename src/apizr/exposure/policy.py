"""Explicit publication choices, composed with independent readiness policy."""

from typing import Literal

from pydantic import Field, StrictBool, field_validator

from apizr.capabilities.types import ValueModel, logical_module
from apizr.repository_readiness.policy import Control, ExecutionRequirements, Mode

Interface = Literal["rest", "mcp"]


def capability_id(value: str) -> str:
    parts = value.split(":")
    if len(parts) != 3 or parts[0] != "python":
        raise ValueError("Use an exact python:module:symbol capability ID")
    module, symbol = parts[1:]
    if (
        logical_module(module) != module
        or logical_module(symbol) != symbol
        or "." in symbol
    ):
        raise ValueError("Use a canonical capability ID")
    return value


class Selection(ValueModel):
    include: tuple[str, ...] = ()
    include_all_ready: StrictBool = False
    exclude: tuple[str, ...] = ()

    @field_validator("include", "exclude")
    @classmethod
    def identities(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({capability_id(value) for value in values}))


class Eligibility(ValueModel):
    allow_conditional: StrictBool = False


class Execution(ValueModel):
    # No implied execution mode and no ranking. Empty sets are policy errors.
    allowed: tuple[Mode, ...] = Field(min_length=1)
    require: tuple[Control, ...] = ()

    @field_validator("allowed", "require")
    @classmethod
    def ordered(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))

    def requirements(self) -> ExecutionRequirements:
        return ExecutionRequirements(modes=self.allowed, require_controls=self.require)


class ExposurePolicy(ValueModel):
    schema_version: Literal["apizr.exposure-policy/v1"] = "apizr.exposure-policy/v1"
    selection: Selection = Field(default_factory=Selection)
    interfaces: tuple[Interface, ...] = Field(min_length=1)
    eligibility: Eligibility = Field(default_factory=Eligibility)
    execution: Execution

    @field_validator("interfaces")
    @classmethod
    def ordered(cls, values: tuple[Interface, ...]) -> tuple[Interface, ...]:
        return tuple(sorted(set(values)))
