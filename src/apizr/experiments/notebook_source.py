"""Transient code-cell sidecar; the existing notebook capability exporter is unchanged."""

import ast
import json
from dataclasses import dataclass
from typing import Annotated, Self, cast

from pydantic import Field, model_validator

from apizr.experiments._lexical import MAX_SOURCE_BYTES, bounded_tree
from apizr.experiments.model import ExperimentValue, Reference


class SourceLocation(ExperimentValue):
    source: Reference
    line: Annotated[int, Field(ge=1, le=MAX_SOURCE_BYTES)]
    column: Annotated[int, Field(ge=0, le=MAX_SOURCE_BYTES)]
    cell_index: Annotated[int, Field(ge=0, le=1023)] | None = None
    code_cell_index: Annotated[int, Field(ge=0, le=1023)] | None = None
    cell_line: Annotated[int, Field(ge=1, le=MAX_SOURCE_BYTES)] | None = None

    @model_validator(mode="after")
    def complete_cell(self) -> Self:
        fields = (self.cell_index, self.code_cell_index, self.cell_line)
        if any(v is None for v in fields) and any(v is not None for v in fields):
            raise ValueError("incomplete_cell_location")
        return self


@dataclass(frozen=True)
class CellSpan:
    cell_index: int
    code_cell_index: int
    first_line: int
    last_line: int


@dataclass(frozen=True)
class NotebookSource:
    source: str
    cells: tuple[CellSpan, ...]
    exported_positions: dict[tuple[int, int], tuple[int, int]]

    def locate(self, reference: str, line: int, column: int) -> SourceLocation:
        for cell in self.cells:
            if cell.first_line <= line <= cell.last_line:
                return SourceLocation(
                    source=reference,
                    line=line,
                    column=column,
                    cell_index=cell.cell_index,
                    code_cell_index=cell.code_cell_index,
                    cell_line=line - cell.first_line + 1,
                )
        raise ValueError("notebook_location_unmapped")

    def locate_exported(self, reference: str, line: int) -> SourceLocation:
        positions = [
            (column, target)
            for (number, column), target in self.exported_positions.items()
            if number == line
        ]
        if not positions:
            raise ValueError("notebook_export_location_unmapped")
        return self.locate(reference, *min(positions)[1])


def code_cells(raw: bytes) -> NotebookSource:
    """Bound code cells before passing the notebook to the existing exporter.

    Cell indexes are zero-based: both the full notebook cells array and its code-only
    subsequence are retained. Counts, outputs and markdown never enter this source.
    The unchanged exporter subsequently validates full notebook structure.
    """
    decoded: object = json.loads(raw)
    if not isinstance(decoded, dict):
        raise ValueError("notebook_cells_invalid")
    notebook = cast(dict[str, object], decoded)
    records = notebook.get("cells")
    if notebook.get("nbformat") != 4 or not isinstance(records, list):
        raise ValueError("notebook_cells_invalid")
    records = cast(list[object], records)
    if len(records) > 1024:
        raise ValueError("notebook_cells_invalid")
    chunks: list[str] = []
    cells: list[CellSpan] = []
    line = 1
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError("notebook_cell_invalid")
        cell = cast(dict[str, object], record)
        if cell.get("cell_type") not in (
            "code",
            "markdown",
            "raw",
        ):
            raise ValueError("notebook_cell_invalid")
        if cell["cell_type"] != "code":
            continue
        source = cell.get("source")
        if isinstance(source, list):
            pieces = cast(list[object], source)
            if any(not isinstance(piece, str) for piece in pieces):
                raise ValueError("notebook_cell_source_invalid")
            source = "".join(cast(list[str], pieces))
        if not isinstance(source, str):
            raise ValueError("notebook_cell_source_invalid")
        # Universal newlines match Python's parser without trimming cell-local blanks.
        source = source.replace("\r\n", "\n").replace("\r", "\n")
        bounded_tree(source)  # A code cell must parse independently as ordinary Python.
        count = source.count("\n") + 1
        cells.append(CellSpan(index, len(cells), line, line + count - 1))
        chunks.append(source + "\n\n")
        line += count + 1
    combined = "".join(chunks)
    bounded_tree(combined)
    return NotebookSource(combined, tuple(cells), {})


def map_exported(notebook: NotebookSource, exported: str) -> NotebookSource:
    """Prove AST equivalence; map nodes without trusting exporter comment markers."""
    tree = bounded_tree(notebook.source)
    original = bounded_tree(exported)
    if ast.dump(tree, include_attributes=False) != ast.dump(
        original, include_attributes=False
    ):
        raise ValueError("notebook_source_mapping_disagrees")
    positions: dict[tuple[int, int], tuple[int, int]] = {}
    for generated, cell_node in zip(ast.walk(original), ast.walk(tree), strict=True):
        if isinstance(
            generated,
            (ast.expr, ast.stmt, ast.arg, ast.keyword, ast.alias, ast.excepthandler),
        ) and isinstance(
            cell_node,
            (ast.expr, ast.stmt, ast.arg, ast.keyword, ast.alias, ast.excepthandler),
        ):
            positions[(generated.lineno, generated.col_offset)] = (
                cell_node.lineno,
                cell_node.col_offset,
            )
    return NotebookSource(notebook.source, notebook.cells, positions)
