"""Public bounded source/lexical input for static scientific recognition."""

import ast
import hashlib
from collections.abc import Callable
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from apizr.contracts.distribution import Digest
from apizr.experiments._lexical import (
    MAX_DEPTH,
    MAX_NODES,
    MAX_SOURCE_BYTES,
    LexicalVisitor,
    SourceLimit,
    bounded_tree,
)
from apizr.experiments.model import ExperimentValue, Reference


class SourceView(ExperimentValue):
    """Exact UTF-8 source; a fresh bounded AST prevents shared mutable authority."""

    schema_version: Literal["apizr.scientific-source/v1"] = "apizr.scientific-source/v1"
    reference: Reference
    text: Annotated[str, Field(max_length=MAX_SOURCE_BYTES)]

    @model_validator(mode="after")
    def bounded_source(self) -> Self:
        self.tree()
        return self

    @property
    def digest(self) -> Digest:
        """Computed by the core from admitted bytes, never supplied by a provider."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def tree(
        self,
        *,
        max_bytes: int = MAX_SOURCE_BYTES,
        max_nodes: int = MAX_NODES,
        max_depth: int = MAX_DEPTH,
    ) -> ast.Module:
        """Providers may lower the core's bounds, never raise them."""
        try:
            if not (
                1 <= max_bytes <= MAX_SOURCE_BYTES
                and 1 <= max_nodes <= MAX_NODES
                and 1 <= max_depth <= MAX_DEPTH
            ):
                raise ValueError("source_view_bounds")
            return bounded_tree(
                self.text,
                max_bytes=max_bytes,
                max_nodes=max_nodes,
                max_depth=max_depth,
            )
        except (SourceLimit, ValueError, UnicodeError, SyntaxError, RecursionError):
            raise ValueError("provider_source_invalid_or_limit") from None

    def contains_location(self, line: int, column: int) -> bool:
        """AST columns are UTF-8 byte offsets, with a zero-based column."""
        lines = self.text.splitlines()
        return 1 <= line <= len(lines) and 0 <= column <= len(
            lines[line - 1].encode("utf-8")
        )


class SourceLexicalVisitor(LexicalVisitor):
    """Supported lexical authority with explicit provider import allowlists.

    Inherited scope handling rejects shadowing, star imports and unsupported
    generic scopes. Call resolution is evidence of syntax, never execution.
    """

    def __init__(
        self, modules: Callable[[str], bool], members: Callable[[str], bool]
    ) -> None:
        super().__init__(modules, members)
