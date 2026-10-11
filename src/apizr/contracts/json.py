"""Finite JSON for admission and extensions, without importing execution workers.

The embedded execution protocol retains its standalone artifact implementation."""

import json

from pydantic import ConfigDict, JsonValue, TypeAdapter

MAX_REQUEST_BYTES = 64 * 1024 * 1024
JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(
    JsonValue, config=ConfigDict(allow_inf_nan=False)
)


class ProtocolError(ValueError):
    pass


class SizeExceeded(ProtocolError):
    pass


def finite_json(value: object) -> JsonValue:
    return JSON_VALUE.validate_python(value, strict=True)


def encode(value: object, limit: int) -> bytes:
    result = bytearray()
    value = finite_json(value)
    encoder = json.JSONEncoder(
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    for chunk in encoder.iterencode(value):
        raw = chunk.encode("utf-8")
        if len(result) + len(raw) > limit:
            raise SizeExceeded("frame_size")
        result.extend(raw)
    if len(result) + 1 > limit:
        raise SizeExceeded("frame_size")
    return bytes(result) + b"\n"
