"""Transport-neutral JSON inputs and callable invocation contracts."""

from typing import Literal

from apizr.capabilities.model import ParameterKind
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


class InvocationContract(ValueModel):
    capability_id: str
    name: str
    execution: Literal["sync", "async"]
    parameters: tuple[Input, ...]
    returns: TypeSpec
    description: str | None = None
