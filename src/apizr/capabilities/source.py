"""Admission budgets for explicitly selected Python and notebook source bytes."""

import ast
from collections.abc import Iterator
from pathlib import Path

from apizr.contracts.json_budget import preflight_json
from apizr.workspace.files import read_regular

# Match the repository scanner's maximum per-source budget and the existing
# experiment notebook byte budget. Experiment Python inspection stays stricter.
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_NOTEBOOK_BYTES = 16 * 1024 * 1024
MAX_AST_NODES = 100_000
MAX_AST_DEPTH = 128
MAX_NOTEBOOK_NODES = 100_000
MAX_NOTEBOOK_DEPTH = 64


def read_source(path: str | Path) -> bytes:
    """Follow the explicitly selected alias, then read a bounded regular file."""
    selected = Path(path)
    if selected.suffix not in {".py", ".ipynb"}:
        raise ValueError("Source supports one .py or .ipynb file")
    return read_regular(
        selected.resolve(strict=True),
        MAX_SOURCE_BYTES if selected.suffix == ".py" else MAX_NOTEBOOK_BYTES,
    )


def notebook_text(raw: bytes | str) -> str:
    return preflight_json(
        raw,
        max_bytes=MAX_NOTEBOOK_BYTES,
        max_nodes=MAX_NOTEBOOK_NODES,
        max_depth=MAX_NOTEBOOK_DEPTH,
    )


def check_tree(tree: ast.Module) -> None:
    """Stop recursive analysis before traversing an oversized or deep AST."""
    pending: list[tuple[Iterator[ast.AST], int]] = [(iter((tree,)), 0)]
    count = 0
    while pending:
        children, depth = pending[-1]
        node = next(children, None)
        if node is None:
            pending.pop()
            continue
        count += 1
        if count > MAX_AST_NODES or depth > MAX_AST_DEPTH:
            raise ValueError("source_structure_limit")
        pending.append((ast.iter_child_nodes(node), depth + 1))
