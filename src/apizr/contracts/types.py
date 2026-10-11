"""Frozen JSON value contracts shared by static evidence and all interfaces."""

import keyword
from typing import Any, Literal, Self

from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

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
        "object",
    ]
    items: tuple["TypeSpec", ...] = ()
    values: tuple[Scalar, ...] = ()
    variadic: bool = False
    fields: tuple["ObjectField", ...] = ()

    @field_validator("fields")
    @classmethod
    def ordered_unique(
        cls, fields: tuple["ObjectField", ...]
    ) -> tuple["ObjectField", ...]:
        if len({field.name for field in fields}) != len(fields):
            raise ValueError("Duplicate object fields")
        return tuple(sorted(fields, key=lambda field: field.name))

    @model_validator(mode="after")
    def object_shape(self) -> Self:
        if self.kind == "object":
            if self.items or self.values or self.variadic:
                raise ValueError("Object contracts use only typed fields")
        elif self.fields:
            raise ValueError("Only object contracts can have fields")
        return self

    @model_serializer(mode="wrap")
    def serialize(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result = handler(self)
        # Keep every historical non-object contract's canonical bytes unchanged.
        if self.kind != "object" and not self.fields:
            result.pop("fields", None)
        return result


class ObjectField(ValueModel):
    name: str
    required: bool = Field(strict=True)
    type: TypeSpec

    @field_validator("name")
    @classmethod
    def identifier(cls, name: str) -> str:
        if not name.isidentifier() or keyword.iskeyword(name):
            raise ValueError("Object field must be a Python identifier")
        return name

    @model_validator(mode="after")
    def valid_type(self) -> Self:
        pending = [self.type]
        while pending:
            spec = pending.pop()
            if spec.kind in {"list", "dict", "set"} or (
                spec.kind == "tuple" and spec.variadic
            ):
                if len(spec.items) != 1:
                    raise ValueError("Object field container needs one item contract")
            elif spec.kind == "union" and not spec.items:
                raise ValueError("Object field union needs member contracts")
            elif spec.kind == "literal" and not spec.values:
                raise ValueError("Object field literal needs scalar choices")
            elif spec.kind not in {"union", "tuple", "object"} and spec.items:
                raise ValueError("Object field scalar cannot have item contracts")
            if (spec.kind != "literal" and spec.values) or (
                spec.kind != "tuple" and spec.variadic
            ):
                raise ValueError("Object field has inconsistent type details")
            pending.extend(spec.items)
        return self


TypeSpec.model_rebuild()
