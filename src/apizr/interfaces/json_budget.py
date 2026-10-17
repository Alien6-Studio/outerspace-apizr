"""Portable admission budgets for transport JSON graphs and their wire encoding."""

import json
import math
from typing import TypeAlias, cast

from apizr.contracts.json_budget import preflight_json

JSON: TypeAlias = None | bool | int | float | str | list["JSON"] | dict[str, "JSON"]

MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_JSON_NODES = 100_000
MAX_JSON_DEPTH = 64


def preflight(raw: bytes | str, *, max_bytes: int = MAX_JSON_BYTES) -> str:
    return preflight_json(
        raw,
        max_bytes=max_bytes,
        max_nodes=MAX_JSON_NODES,
        max_depth=MAX_JSON_DEPTH,
    )


class JsonBudget:
    """Bound traversal and exact compact UTF-8 JSON size before copying/encoding.

    Count keys as nodes, reject broad containers before iteration and charge
    strings in small pieces: a single escaped string must not bypass the budget
    by allocating a large encoder chunk first. State belongs to one traversal.
    """

    def __init__(
        self,
        *,
        max_bytes: int = MAX_JSON_BYTES,
        max_nodes: int = MAX_JSON_NODES,
        max_depth: int = MAX_JSON_DEPTH,
    ) -> None:
        self.remaining_bytes = max_bytes
        self.remaining_nodes = max_nodes
        self.max_depth = max_depth

    def charge(self, size: int) -> None:
        self.remaining_bytes -= size
        if self.remaining_bytes < 0:
            raise ValueError("json_byte_limit")

    def string(self, value: str) -> None:
        # Every code point occupies at least one wire byte.
        if len(value) + 2 > self.remaining_bytes:
            raise ValueError("json_byte_limit")
        self.charge(2)
        for offset in range(0, len(value), 4096):
            piece = json.dumps(value[offset : offset + 4096], ensure_ascii=False)
            self.charge(len(piece[1:-1].encode("utf-8")))

    def visit(
        self,
        value: object,
        *,
        copy: bool = False,
        tuples: bool = False,
        sets: bool = False,
        depth: int = 0,
    ) -> JSON:
        self.remaining_nodes -= 1
        if self.remaining_nodes < 0:
            raise ValueError("json_node_limit")
        if value is None or isinstance(value, (bool, int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Result is not a finite JSON value")
            if (
                isinstance(value, int)
                and value.bit_length() * 3 // 10 > self.remaining_bytes
            ):
                raise ValueError("json_byte_limit")
            self.charge(len(json.dumps(value, allow_nan=False)))
            return value
        if isinstance(value, str):
            self.string(value)
            return value
        sequence = (
            isinstance(value, list)
            or (tuples and isinstance(value, tuple))
            or (sets and isinstance(value, (set, frozenset)))
        )
        if isinstance(value, dict) or sequence:
            if depth >= self.max_depth:
                raise ValueError("json_depth_limit")
            container = cast("dict[object, object] | list[object]", value)
            count = len(container)
            if count * (2 if isinstance(value, dict) else 1) > self.remaining_nodes:
                raise ValueError("json_node_limit")
            self.charge(2 + max(0, count - 1))
            if isinstance(value, dict):
                result: dict[str, JSON] = {}
                dictionary = cast(dict[object, object], value)
                for key, item in dictionary.items():
                    if not isinstance(key, str):
                        raise ValueError("Result is not a finite JSON value")
                    self.visit(key)
                    self.charge(1)
                    child = self.visit(
                        item, copy=copy, tuples=tuples, sets=sets, depth=depth + 1
                    )
                    if copy:
                        result[key] = child
                return result if copy else cast(JSON, value)
            items: list[JSON] = []
            for item in container:
                child = self.visit(
                    item, copy=copy, tuples=tuples, sets=sets, depth=depth + 1
                )
                if copy:
                    items.append(child)
            return items if copy else cast(JSON, value)
        raise ValueError("Result is not a finite JSON value")


def bounded_dumps(value: object, *, max_bytes: int = MAX_JSON_BYTES) -> str:
    JsonBudget(max_bytes=max_bytes).visit(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
