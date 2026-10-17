"""Bounded, deeply immutable JSON values for explicit experiment controls."""

import math
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Annotated, TypeAlias, cast

from pydantic import AfterValidator, BeforeValidator, Field, JsonValue, PlainSerializer
from typing_extensions import TypeAliasType

MAX_DEPTH = 16
MAX_NODES = 4096
MAX_VALUE_BYTES = 65536
_CONTROL = re.compile(r"[\x00-\x1f]")


def json_string_size(value: str) -> int:
    """Exact compact UTF-8 JSON string size, without creating escaped JSON."""
    return (
        len(value.encode("utf-8"))
        + 2
        + value.count('"')
        + value.count("\\")
        + sum(
            1 if match[0] in "\b\t\n\f\r" else 5 for match in _CONTROL.finditer(value)
        )
    )


# The explicit recursive alias also supports static checkers on Python 3.11.
if TYPE_CHECKING:
    FrozenJSON: TypeAlias = (
        None
        | bool
        | int
        | float
        | str
        | tuple["FrozenJSON", ...]
        | Mapping[str, "FrozenJSON"]
    )
else:
    FrozenJSON = TypeAliasType(
        "FrozenJSON",
        bool
        | None
        | Annotated[int, Field(ge=-(2**63), le=2**63 - 1)]
        | Annotated[float, Field(allow_inf_nan=False)]
        | Annotated[str, Field(max_length=8192)]
        | Annotated[tuple["FrozenJSON", ...], Field(max_length=1024)]
        | Annotated[
            Mapping[Annotated[str, Field(max_length=256)], "FrozenJSON"],
            Field(max_length=1024),
        ],
    )


def _thaw(value: FrozenJSON) -> JsonValue:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _freeze(value: object) -> FrozenJSON:
    remaining = MAX_NODES
    remaining_bytes = MAX_VALUE_BYTES

    def charge(size: int) -> None:
        nonlocal remaining_bytes
        remaining_bytes -= size
        if remaining_bytes < 0:
            raise ValueError("experiment_value_byte_size")

    def visit(item: object, depth: int) -> FrozenJSON:
        nonlocal remaining
        remaining -= 1
        if depth > MAX_DEPTH or remaining < 0:
            raise ValueError("experiment_value_complexity")
        if item is None or type(item) is bool:
            charge(4 if item is None or item else 5)
            return item
        if type(item) is int:
            integer = item
            if not -(2**63) <= integer < 2**63:
                raise ValueError("experiment_value_integer_range")
            charge(len(str(integer)))
            return integer
        if type(item) is float:
            number = item
            if not math.isfinite(number):
                raise ValueError("experiment_value_non_finite")
            charge(len(repr(number)))
            return number
        if type(item) is str:
            string = item
            if len(string) > 8192:
                raise ValueError("experiment_value_string_size")
            charge(json_string_size(string))
            return string
        if type(item) in (list, tuple):
            sequence = cast("list[object] | tuple[object, ...]", item)
            if len(sequence) > 1024:
                raise ValueError("experiment_value_collection_size")
            charge(2 + max(0, len(sequence) - 1))
            return tuple(visit(child, depth + 1) for child in sequence)
        if type(item) in (dict, MappingProxyType):
            mapping = cast("Mapping[object, object]", item)
            if len(mapping) > 1024:
                raise ValueError("experiment_value_collection_size")
            charge(2 + max(0, len(mapping) - 1))
            result: dict[str, FrozenJSON] = {}
            for key, child in mapping.items():
                if type(key) is not str or len(key) > 256:
                    raise ValueError("experiment_value_object_key")
                charge(json_string_size(key) + 1)
                result[key] = visit(child, depth + 1)
            return MappingProxyType(result)
        raise ValueError("experiment_value_not_json")

    return visit(value, 0)


FiniteValue: TypeAlias = Annotated[
    FrozenJSON,
    BeforeValidator(_freeze),
    AfterValidator(_freeze),
    PlainSerializer(_thaw, return_type=JsonValue, when_used="json"),
]
