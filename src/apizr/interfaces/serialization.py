"""Deterministic REST artifacts; hashes are external to their own document."""

import json

from pydantic import JsonValue


def json_bytes(value: JsonValue) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
