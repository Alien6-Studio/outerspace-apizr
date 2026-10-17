"""Immutable source facts owned by one inspection; mutable trees never escape here."""

import ast
import hashlib
from dataclasses import dataclass

from apizr.experiments._lexical import (
    MAX_DEPTH,
    MAX_NODES,
    MAX_SOURCE_BYTES,
    SourceLimit,
    bounded_tree,
)


@dataclass(frozen=True, slots=True, init=False)
class SourceAnalysis:
    source: str
    digest: str
    byte_size: int
    node_count: int
    depth: int
    line_bytes: tuple[int, ...]

    def __init__(self, source: str):
        tree = bounded_tree(source)
        pending: list[tuple[ast.AST, int]] = [(tree, 0)]
        count = depth = 0
        while pending:
            node, level = pending.pop()
            count += 1
            depth = max(depth, level)
            pending.extend((child, level + 1) for child in ast.iter_child_nodes(node))
        raw = source.encode("utf-8")
        lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if lines[-1] == "":
            lines.pop()
        for name, value in (
            ("source", source),
            ("digest", hashlib.sha256(raw).hexdigest()),
            ("byte_size", len(raw)),
            ("node_count", count),
            ("depth", depth),
            ("line_bytes", tuple(len(line.encode("utf-8")) for line in lines)),
        ):
            object.__setattr__(self, name, value)

    def check(
        self,
        *,
        max_bytes: int = MAX_SOURCE_BYTES,
        max_nodes: int = MAX_NODES,
        max_depth: int = MAX_DEPTH,
    ) -> None:
        if any(
            type(value) is not int or not 1 <= value <= ceiling
            for value, ceiling in (
                (max_bytes, MAX_SOURCE_BYTES),
                (max_nodes, MAX_NODES),
                (max_depth, MAX_DEPTH),
            )
        ):
            raise ValueError("source_view_bounds")
        if self.byte_size > max_bytes:
            raise SourceLimit(parsed=False)
        if self.node_count > max_nodes or self.depth > max_depth:
            raise SourceLimit(parsed=True)
