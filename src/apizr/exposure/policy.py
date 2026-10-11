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
    include: tuple[str, ...] = Field(
        default=(),
        description="Exact canonical capability IDs explicitly proposed for exposure, for example python:model:predict. No fuzzy matching or implicit dependency exposure.",
    )
    include_all_ready: StrictBool = Field(
        default=False,
        description="Add capabilities assessed READY in the repository readiness report to the requested selection before exclusions. All planner eligibility, interface and execution checks still apply; this grants no publication or operator authority.",
    )
    exclude: tuple[str, ...] = Field(
        default=(),
        description="Exact capability IDs removed after combining include and include_all_ready. Unknown IDs in either include or exclude are refused.",
    )

    @field_validator("include", "exclude")
    @classmethod
    def identities(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({capability_id(value) for value in values}))


class Eligibility(ValueModel):
    allow_conditional: StrictBool = Field(
        default=False,
        description="Allow selected capabilities with CONDITIONAL readiness in their required repository evidence to be proposed, subject to all other planner checks. CONDITIONAL does not become READY; ambiguous or unsupported evidence is not made eligible.",
    )


class Execution(ValueModel):
    # No implied execution mode and no ranking. Empty sets are policy errors.
    allowed: tuple[Mode, ...] = Field(
        min_length=1,
        description="Explicit nonempty set of acceptable execution modes. No ranking, implicit default or fallback. Compatibility must also satisfy the startup readiness policy; selecting a mode does not execute or authorize anything.",
    )
    require: tuple[Control, ...] = Field(
        default=(),
        description="Explicit execution controls that every compatible proposed mode must support. These requirements narrow compatibility; they do not grant operator permissions or attest to a live runtime.",
    )

    @field_validator("allowed", "require")
    @classmethod
    def ordered(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))

    def requirements(self) -> ExecutionRequirements:
        return ExecutionRequirements(modes=self.allowed, require_controls=self.require)


class ExposurePolicy(ValueModel):
    schema_version: Literal["apizr.exposure-policy/v1"] = Field(
        default="apizr.exposure-policy/v1",
        description="Version identifier for this exposure planning constraint contract; not operator authorization.",
    )
    selection: Selection = Field(
        default_factory=Selection,
        description="Explicit capability selection proposal; empty defaults do not select every capability.",
    )
    interfaces: tuple[Interface, ...] = Field(
        min_length=1,
        description="Nonempty requested generated interface set: rest and/or mcp. Planning checks compatibility for every interface; it does not generate, deploy or run them.",
    )
    eligibility: Eligibility = Field(
        default_factory=Eligibility,
        description="Readiness eligibility constraints for selected capabilities; cannot replace missing or uncertain evidence.",
    )
    execution: Execution = Field(
        description="Explicit acceptable execution modes and required controls for compatibility planning, not permission to execute."
    )

    @field_validator("interfaces")
    @classmethod
    def ordered(cls, values: tuple[Interface, ...]) -> tuple[Interface, ...]:
        return tuple(sorted(set(values)))
