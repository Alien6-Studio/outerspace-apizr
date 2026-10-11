"""Independent, explicit requirements over existing static evidence."""

from typing import Literal

from pydantic import Field, StrictBool, field_validator

from apizr.capabilities.types import ValueModel
from apizr.contracts.dependencies import DependencyWheel
from apizr.execution.policy import EffectName

# Readiness requirements are transport-neutral and independent of runtime policy
# schemas. Keep every original v1 spelling while completing the static vocabulary.
Control = Literal[
    "wall_timeout",
    "input_limit",
    "output_limit",
    "environment",
    "working_directory",
    "network_deny",
    "filesystem_sandbox",
    "subprocess_deny",
    "memory_limit",
    "cpu_limit",
    "pid_limit",
]
Mode = Literal["direct", "local-process", "oci-container"]


class EffectRequirements(ValueModel):
    require_known: tuple[EffectName, ...] = ()
    require_false: tuple[EffectName, ...] = ()

    @field_validator("require_known", "require_false")
    @classmethod
    def ordered(cls, values: tuple[EffectName, ...]) -> tuple[EffectName, ...]:
        return tuple(sorted(set(values)))


class RelationshipRequirements(ValueModel):
    require_resolved: StrictBool = True


class ExecutionRequirements(ValueModel):
    modes: tuple[Mode, ...] = ("local-process", "oci-container")
    require_controls: tuple[Control, ...] = ()

    @field_validator("modes")
    @classmethod
    def ordered_modes(cls, values: tuple[Mode, ...]) -> tuple[Mode, ...]:
        if not values:
            raise ValueError("Declare at least one execution mode")
        return tuple(sorted(set(values)))

    @field_validator("require_controls")
    @classmethod
    def ordered_controls(cls, values: tuple[Control, ...]) -> tuple[Control, ...]:
        return tuple(sorted(set(values)))


class RepositoryReadinessPolicy(ValueModel):
    schema_version: Literal["apizr.repository-readiness-policy/v1"] = (
        "apizr.repository-readiness-policy/v1"
    )
    effects: EffectRequirements = Field(default_factory=EffectRequirements)
    relationships: RelationshipRequirements = Field(
        default_factory=RelationshipRequirements
    )
    execution: ExecutionRequirements = Field(default_factory=ExecutionRequirements)
    # Repository eligibility retains local blockers except proven local imports.
    # This additionally makes remaining interface uncertainty unsupported.
    require_interface: StrictBool = False
    dependency_wheels: tuple[DependencyWheel, ...] = Field(
        default=(), max_length=128, exclude_if=lambda value: not value
    )

    @field_validator("dependency_wheels")
    @classmethod
    def unique_providers(
        cls, values: tuple[DependencyWheel, ...]
    ) -> tuple[DependencyWheel, ...]:
        names = [wheel.pin.split("==")[0] for wheel in values]
        modules = [module for wheel in values for module in wheel.modules]
        if len(set(names)) != len(names) or len(set(modules)) != len(modules):
            raise ValueError("Dependency wheel providers must be unambiguous")
        return tuple(sorted(values, key=lambda wheel: wheel.pin))
