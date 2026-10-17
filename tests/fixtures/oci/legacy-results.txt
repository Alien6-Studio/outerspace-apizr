"""Finite JSON validation and explicit Python-result transport normalization."""

import math
from typing import TypeGuard

from apizr.interfaces.runtime import JSON


def _sequence(value: object) -> TypeGuard[list[object] | tuple[object, ...]]:
    return isinstance(value, (list, tuple))


def _dictionary(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _value(value: object, *, allow_tuples: bool) -> JSON:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if _sequence(value) and (allow_tuples or isinstance(value, list)):
        return [_value(item, allow_tuples=allow_tuples) for item in value]
    if _dictionary(value) and all(isinstance(key, str) for key in value):
        return {
            str(key): _value(item, allow_tuples=allow_tuples)
            for key, item in value.items()
        }
    raise ValueError("Result is not a finite JSON value")


def finite_json_value(value: object) -> JSON:
    """Validate transport input without admitting Python tuples or coercion."""
    return _value(value, allow_tuples=False)


def normalize_result_for_json(value: object) -> JSON:
    """Copy lists/dicts and recursively lower Python result tuples to JSON arrays.

    Tuples are accepted only at this result boundary, not as JSON themselves.
    Unsupported objects and non-finite floats are never coerced or stringified.
    Recursive containers retain the callers' controlled RecursionError handling.
    """
    return _value(value, allow_tuples=True)
