"""Account admitted capture bytes without serializing observations during logging."""

from collections.abc import Mapping
from typing import Callable, cast

from pydantic import TypeAdapter

from apizr.experiments.capture_model import CallParameter
from apizr.experiments.model import (
    ExperimentValue,
    InputArtifact,
    Metric,
    OutputArtifact,
    Parameter,
)
from apizr.experiments.values import json_string_size

_FLOAT = TypeAdapter(float)
# Fixed, bounded schema metadata only; no user values, files or observations are
# cached. These are the five canonical kinds admitted by the SDK's logging API.
_FIELDS: dict[
    type[ExperimentValue], tuple[tuple[str, int, Callable[[object], bool] | None], ...]
] = {
    model: tuple(
        (name, json_string_size(name) + 1, field.exclude_if)
        for name, field in model.model_fields.items()
    )
    for model in (Parameter, Metric, InputArtifact, OutputArtifact, CallParameter)
}


def _value_size(value: object) -> int:
    if value is None:
        return 4
    if isinstance(value, bool):
        return 4 if value else 5
    if isinstance(value, str):
        return json_string_size(value)
    if isinstance(value, int):
        return len(str(value))
    if isinstance(value, float):
        # Use the installed serializer's numeric token: its exponent spelling
        # can differ from Python's repr. No enclosing value/record is encoded.
        return len(_FLOAT.dump_json(value))
    if isinstance(value, Mapping):
        mapping = cast(Mapping[str, object], value)
        return (
            2
            + max(0, len(mapping) - 1)
            + sum(
                json_string_size(key) + 1 + _value_size(item)
                for key, item in mapping.items()
            )
        )
    if isinstance(value, tuple):
        sequence = cast(tuple[object, ...], value)
        return (
            2 + max(0, len(sequence) - 1) + sum(_value_size(item) for item in sequence)
        )
    raise TypeError("tracking_budget_requires_admitted_value")


def capture_size(value: ExperimentValue) -> int:
    """Exact model_dump_json UTF-8 size for one admitted, immutable observation."""
    fields = _FIELDS[type(value)]
    size, count = 2, 0
    for name, key_size, exclude_if in fields:
        item = getattr(value, name)
        if exclude_if is not None and exclude_if(item):
            continue
        size += key_size + _value_size(item)
        count += 1
    return size + max(0, count - 1)
