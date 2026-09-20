"""Versioned REST plan and artifact contract, separate from IR/readiness."""

from typing import Literal

from apizr.capabilities.model import Digest, ParameterKind, Source
from apizr.capabilities.types import ValueModel

Scalar = str | int | float | bool | None


class TypeSpec(ValueModel):
    kind: Literal[
        "any",
        "int",
        "str",
        "float",
        "bool",
        "null",
        "list",
        "dict",
        "tuple",
        "set",
        "union",
        "literal",
    ]
    items: tuple["TypeSpec", ...] = ()
    values: tuple[Scalar, ...] = ()
    variadic: bool = False


class Input(ValueModel):
    name: str
    kind: ParameterKind
    required: bool
    type: TypeSpec


class Endpoint(ValueModel):
    capability_id: str
    name: str
    route: str
    method: Literal["POST"] = "POST"
    execution: Literal["sync", "async"]
    parameters: tuple[Input, ...]
    returns: TypeSpec
    description: str | None = None


class RestPlan(ValueModel):
    schema_version: Literal["apizr.rest/v1"] = "apizr.rest/v1"
    source: Source
    executable_digest: Digest
    executable_path: str
    ir_digest: Digest
    readiness_digest: Digest
    endpoints: tuple[Endpoint, ...]


class Manifest(ValueModel):
    schema_version: Literal["apizr.rest/v1"] = "apizr.rest/v1"
    source: Source
    executable_digest: Digest
    executable_path: str
    ir_digest: Digest
    readiness_digest: Digest
    capabilities: tuple[Endpoint, ...]
    artifacts: dict[str, Digest]
