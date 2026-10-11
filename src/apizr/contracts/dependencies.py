"""Declarative wheel import evidence, independent of scientific frameworks."""

from pydantic import Field, field_validator

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel, logical_module
from apizr.contracts.application import dependency_pins, resource_path


class DependencyWheel(ValueModel):
    """Retained wheel identity and statically observed importable modules.

    This establishes a provider for imports, not API compatibility, safe module
    initialization or a successful future invocation. Consumers retain that
    uncertainty and require explicit conditional exposure.
    """

    pin: str
    filename: str = Field(max_length=255)
    digest: Digest
    modules: tuple[str, ...] = Field(min_length=1, max_length=10000)

    @field_validator("pin")
    @classmethod
    def exact_pin(cls, value: str) -> str:
        return dependency_pins((value,))[0]

    @field_validator("filename")
    @classmethod
    def wheel_filename(cls, value: str) -> str:
        if resource_path(value) != value or "/" in value or not value.endswith(".whl"):
            raise ValueError("Expected a wheel filename")
        return value

    @field_validator("modules")
    @classmethod
    def module_names(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({logical_module(value) for value in values}))
