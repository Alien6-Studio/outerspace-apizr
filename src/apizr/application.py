"""Explicit application inputs, independent of core and plugin environments."""

import re
from typing import Self

from pydantic import Field, field_validator, model_validator

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel
from apizr.repository.policy import relative_path

MAX_RESOURCE_BYTES = 16 * 1024 * 1024
MAX_APPLICATION_BYTES = 32 * 1024 * 1024
PIN = re.compile(
    r"([A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?)=="
    r"((?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?"
    r"(?:\.post[0-9]+)?(?:\.dev[0-9]+)?(?:\+[a-z0-9]+(?:[._-][a-z0-9]+)*)?)"
)


def dependency_pins(values: tuple[str, ...]) -> tuple[str, ...]:
    """Small exact-pin subset; no URLs, options, markers, extras or resolution."""
    pins: dict[str, str] = {}
    for value in values:
        match = PIN.fullmatch(value)
        if match is None or len(value) > 256:
            raise ValueError(
                "Application dependencies require exact name==version pins"
            )
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        if name in pins:
            raise ValueError("Duplicate application dependency")
        pins[name] = name + "==" + match[2]
    return tuple(pins[name] for name in sorted(pins))


def resource_path(value: str) -> str:
    normalized = relative_path(value)
    if len(normalized) > 512 or any(
        part.startswith(".") or any(ord(char) < 32 or ord(char) == 127 for char in part)
        for part in normalized.split("/")
    ):
        raise ValueError("Application resources require nonhidden relative file paths")
    return normalized


class ApplicationConfig(ValueModel):
    dependencies: tuple[str, ...] = Field(default=(), max_length=128)
    resources: tuple[str, ...] = Field(default=(), max_length=128)

    _dependencies = field_validator("dependencies")(dependency_pins)

    @field_validator("resources")
    @classmethod
    def resource_files(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(resource_path(value) for value in values)
        if len(set(normalized)) != len(normalized):
            raise ValueError("Duplicate application resource")
        return tuple(sorted(normalized))


class ApplicationResource(ValueModel):
    path: str
    digest: Digest
    size: int = Field(ge=0, le=MAX_RESOURCE_BYTES)

    _path = field_validator("path")(resource_path)


class ApplicationInputs(ValueModel):
    """Bounded bundle extension; not a publication or delivery manifest."""

    dependencies: tuple[str, ...] = Field(default=(), max_length=128)
    resources: tuple[ApplicationResource, ...] = Field(default=(), max_length=128)
    repository_digest: Digest

    _dependencies = field_validator("dependencies")(dependency_pins)

    @model_validator(mode="after")
    def canonical_resources(self) -> Self:
        paths = [resource.path for resource in self.resources]
        if paths != sorted(set(paths)):
            raise ValueError("Expected ordered unique application resources")
        if sum(resource.size for resource in self.resources) > MAX_APPLICATION_BYTES:
            raise ValueError("Application resources exceed aggregate size limit")
        return self

    def requirements(self) -> bytes:
        return "".join(pin + "\n" for pin in self.dependencies).encode("utf-8")
