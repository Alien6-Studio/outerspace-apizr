"""Bounded, deeply immutable JSON values for explicit experiment controls."""

import json
import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Annotated, TypeAlias, cast

from pydantic import AfterValidator, BeforeValidator, Field, JsonValue, PlainSerializer
from typing_extensions import TypeAliasType

MAX_DEPTH = 16
MAX_NODES = 4096
MAX_VALUE_BYTES = 65536

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

    def visit(item: object, depth: int) -> FrozenJSON:
        nonlocal remaining
        remaining -= 1
        if depth > MAX_DEPTH or remaining < 0:
            raise ValueError("experiment_value_complexity")
        if item is None or type(item) is bool:
            return item
        if type(item) is int:
            integer = item
            if not -(2**63) <= integer < 2**63:
                raise ValueError("experiment_value_integer_range")
            return integer
        if type(item) is float:
            number = item
            if not math.isfinite(number):
                raise ValueError("experiment_value_non_finite")
            return number
        if type(item) is str:
            string = item
            if len(string) > 8192:
                raise ValueError("experiment_value_string_size")
            string.encode("utf-8")
            return string
        if type(item) in (list, tuple):
            sequence = cast("list[object] | tuple[object, ...]", item)
            if len(sequence) > 1024:
                raise ValueError("experiment_value_collection_size")
            return tuple(visit(child, depth + 1) for child in sequence)
        if type(item) in (dict, MappingProxyType):
            mapping = cast("Mapping[object, object]", item)
            if len(mapping) > 1024:
                raise ValueError("experiment_value_collection_size")
            result: dict[str, FrozenJSON] = {}
            for key, child in mapping.items():
                if type(key) is not str or len(key) > 256:
                    raise ValueError("experiment_value_object_key")
                key.encode("utf-8")
                result[key] = visit(child, depth + 1)
            return MappingProxyType(result)
        raise ValueError("experiment_value_not_json")

    frozen = visit(value, 0)
    encoded = json.dumps(
        _thaw(frozen),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_VALUE_BYTES:
        raise ValueError("experiment_value_byte_size")
    return frozen


FiniteValue: TypeAlias = Annotated[
    FrozenJSON,
    BeforeValidator(_freeze),
    AfterValidator(_freeze),
    PlainSerializer(_thaw, return_type=JsonValue, when_used="json"),
]
