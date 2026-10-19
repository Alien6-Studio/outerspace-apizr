"""Public bounded source/lexical input for static scientific recognition."""

import ast
from collections.abc import Callable
from typing import Annotated, Literal, Self

from pydantic import Field, ModelWrapValidatorHandler, PrivateAttr, model_validator

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
from apizr.experiments.source_analysis import SourceAnalysis

__all__ = [
    "MAX_DEPTH",
    "MAX_NODES",
    "MAX_SOURCE_BYTES",
    "SourceLimit",
    "bounded_tree",
    "SourceView",
    "SourceLexicalVisitor",
]


class SourceView(ExperimentValue):
    """Exact UTF-8 source; a fresh bounded AST prevents shared mutable authority."""

    schema_version: Literal["apizr.scientific-source/v1"] = "apizr.scientific-source/v1"
    reference: Reference
    text: Annotated[str, Field(max_length=MAX_SOURCE_BYTES)]
    _analysis: SourceAnalysis = PrivateAttr()

    @model_validator(mode="wrap")
    @classmethod
    def bounded_source(
        cls, value: object, handler: ModelWrapValidatorHandler[Self]
    ) -> Self:
        result = handler(value)
        analysis = getattr(value, "_analysis", None) if type(value) is cls else None
        if type(analysis) is SourceAnalysis and analysis.source == result.text:
            result._analysis = analysis
        else:
            try:
                result._analysis = SourceAnalysis(result.text)
            except (SourceLimit, ValueError, UnicodeError, SyntaxError, RecursionError):
                raise ValueError("provider_source_invalid_or_limit") from None
        return result

    @property
    def analysis(self) -> SourceAnalysis:
        return self._analysis

    @property
    def digest(self) -> Digest:
        """Computed by the core from admitted bytes, never supplied by a provider."""
        return self._analysis.digest

    def validate_bounds(
        self,
        *,
        max_bytes: int = MAX_SOURCE_BYTES,
        max_nodes: int = MAX_NODES,
        max_depth: int = MAX_DEPTH,
    ) -> None:
        try:
            self._analysis.check(
                max_bytes=max_bytes, max_nodes=max_nodes, max_depth=max_depth
            )
        except (SourceLimit, ValueError):
            raise ValueError("provider_source_invalid_or_limit") from None

    def tree(
        self,
        *,
        max_bytes: int = MAX_SOURCE_BYTES,
        max_nodes: int = MAX_NODES,
        max_depth: int = MAX_DEPTH,
    ) -> ast.Module:
        """Providers may lower the core's bounds, never raise them."""
        try:
            self.validate_bounds(
                max_bytes=max_bytes, max_nodes=max_nodes, max_depth=max_depth
            )
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
        # Python physical lines use LF, CRLF or CR. Other Unicode separators
        # remain bytes inside strings/comments and must not invent source lines.
        lines = self._analysis.line_bytes
        return 1 <= line <= len(lines) and 0 <= column <= lines[line - 1]


class SourceLexicalVisitor(LexicalVisitor):
    """Supported lexical authority with explicit provider import allowlists.

    Inherited scope handling rejects shadowing, star imports and unsupported
    generic scopes. Call resolution is evidence of syntax, never execution.
    """

    def __init__(
        self, modules: Callable[[str], bool], members: Callable[[str], bool]
    ) -> None:
        super().__init__(modules, members)
