"""Private single-message protocol: uint64 big-endian length + canonical JSON."""

import json
import struct
from typing import BinaryIO

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


def frame(payload: bytes) -> bytes:
    return struct.pack("!Q", len(payload)) + payload


def size(header: bytes, limit: int) -> int:
    if len(header) != 8:
        raise ProtocolError("truncated_header")
    length = struct.unpack("!Q", header)[0]
    if length > limit:
        raise SizeExceeded("frame_size")
    return length


def decode(data: bytes, limit: int) -> JsonValue:
    length = size(data[:8], limit)
    if len(data) != 8 + length:
        raise ProtocolError("invalid_frame_length")
    return finite_json(json.loads(data[8:]))


def read_frame(stream: BinaryIO, limit: int) -> JsonValue:
    header = stream.read(8)
    length = size(header, limit)
    data = stream.read(length)
    if stream.read(1):
        raise ProtocolError("extra_frame_data")
    return decode(header + data, limit)
