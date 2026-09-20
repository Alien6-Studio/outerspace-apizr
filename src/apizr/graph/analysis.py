"""Internal bounded analysis state; no I/O or environment resolution."""

import ast
from dataclasses import dataclass, field
from typing import Literal

from apizr.capabilities.types import Evidence
from apizr.repository import CapabilityEntry, SourceUnit

from .bindings import Site
from .model import (
    Code,
    Diagnostic,
    ExternalNode,
    ImportDeclaration,
    Location,
    Node,
    Relationship,
    RelationshipKind,
    external_id,
)
from .policy import GraphPolicy


class GraphInputError(ValueError):
    code = Code.INPUT


class LimitError(Exception):
    def __init__(
        self, limit: Literal["ast_nodes", "relationships", "calls", "imports", "parser"]
    ):
        self.limit: Literal[
            "ast_nodes", "relationships", "calls", "imports", "parser"
        ] = limit


@dataclass
class Index:
    modules: dict[str, SourceUnit]
    collisions: set[str]
    capabilities: dict[tuple[str, str], CapabilityEntry]
    stable: set[str]
    symbols: dict[str, dict[str, set[str | None]]] = field(
        default_factory=dict[str, dict[str, set[str | None]]]
    )


@dataclass
class Analysis:
    policy: GraphPolicy
    index: Index
    nodes: dict[str, Node]
    relationships: set[Relationship] = field(default_factory=set[Relationship])
    imports: list[ImportDeclaration] = field(default_factory=list[ImportDeclaration])
    diagnostics: set[Diagnostic] = field(default_factory=set[Diagnostic])
    ast_nodes: int = 0
    calls: int = 0
    declarations: int = 0

    def count_tree(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            self.ast_nodes += 1
            self.calls += isinstance(node, ast.Call)
            self.declarations += isinstance(node, (ast.Import, ast.ImportFrom))
            if self.ast_nodes > self.policy.max_ast_nodes:
                raise LimitError("ast_nodes")
            if self.calls > self.policy.max_calls:
                raise LimitError("calls")
            if self.declarations > self.policy.max_imports:
                raise LimitError("imports")

    def diagnostic(self, code: Code, path: str, site: Site) -> None:
        self.diagnostics.add(
            Diagnostic(
                code=code,
                path=path,
                line=getattr(site.node, "lineno", None),
                column=getattr(site.node, "col_offset", None),
            )
        )

    def external(self, module: str) -> str:
        identity = external_id(module)
        self.nodes[identity] = ExternalNode(id=identity, module=module)
        return identity

    def edge(
        self, source: str, target: str, kind: RelationshipKind, location: Location
    ) -> None:
        self.relationships.add(
            Relationship(
                **location.model_dump(),
                source=source,
                target=target,
                kind=kind,
                resolution_evidence=Evidence.OBSERVED
                if kind == RelationshipKind.CONTAINS
                else Evidence.INFERRED,
            )
        )
        if len(self.relationships) > self.policy.max_relationships:
            raise LimitError("relationships")


def location(path: str, site: Site) -> Location:
    node = site.node
    if not isinstance(node, (ast.stmt, ast.expr)):
        raise ValueError("Evidence requires a statement or expression source span")
    return Location(
        path=path,
        line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        column=node.col_offset,
        end_column=node.end_col_offset or 0,
        availability=site.availability,
    )
