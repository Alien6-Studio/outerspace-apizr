"""Refine only dependency reasons proved by retained repository evidence."""

from typing import TYPE_CHECKING

from apizr.graph.model import ImportDeclaration, RelationshipKind, module_id
from apizr.readiness.model import POLICY, Assessment, Code, State, combine

if TYPE_CHECKING:
    from .model import DeclarationAssessment, Relationships


def _proven_import(declaration: ImportDeclaration, facts: "Relationships") -> bool:
    if declaration.availability != "unconditional" or not declaration.names:
        return False
    edges = (*facts.direct, *facts.module_imports)
    for name in declaration.names:
        if name.resolution not in {"module", "capability"}:
            return False
        kind = (
            RelationshipKind.MODULE
            if name.resolution == "module"
            else RelationshipKind.CAPABILITY
        )
        if not any(
            edge.source == declaration.source
            and edge.target == name.target
            and edge.kind == kind
            and edge.path == declaration.path
            and edge.line == declaration.line
            and edge.end_line == declaration.end_line
            and edge.column == declaration.column
            and edge.end_column == declaration.end_column
            and edge.availability == "unconditional"
            for edge in edges
        ):
            return False
        # A private dependency needs a stable binding and execution evidence,
        # not an independently exposable input/output contract.
        dependencies = [
            dependency.local_readiness
            for dependency in facts.dependencies
            if (
                dependency.capability_id == name.target
                if name.resolution == "capability"
                else module_id(dependency.local_readiness.source.module) == name.target
            )
        ]
        if not dependencies or any(
            not dependency.in_ir
            or dependency.dimensions.binding.state != State.READY
            or dependency.dimensions.execution.state != State.READY
            for dependency in dependencies
        ):
            return False
    return True


def interface_state(
    local: Assessment, source_path: str, facts: "Relationships"
) -> State:
    """Keep local evidence immutable; discharge an exact import line only.

    Callers bind these snapshots to Catalog/Graph through validate_report. The
    projection also requires the imported modules' initialization evidence.
    No whole-Graph completeness shortcut, source parsing or package lookup.
    """
    proven: set[int] = set()
    if local.in_ir and facts.state == "resolved":
        declarations: dict[int, list[ImportDeclaration]] = {}
        for declaration in facts.imports:
            if declaration.path == source_path and declaration.source in {
                local.capability_id,
                module_id(local.source.module),
            }:
                declarations.setdefault(declaration.line, []).append(declaration)
        proven = {
            line
            for line, imports in declarations.items()
            if all(_proven_import(declaration, facts) for declaration in imports)
        }
    dimensions = local.dimensions
    return combine(
        tuple(
            POLICY[reason.code][0]
            for dimension in (
                dimensions.binding,
                dimensions.execution,
                dimensions.inputs,
                dimensions.outputs,
            )
            for reason in dimension.reasons
            if not (
                dimension is dimensions.execution
                and reason.code == Code.DEPENDENCY
                and reason.line in proven
            )
        )
    )


def can_generate_interface(assessment: "DeclarationAssessment") -> bool:
    """Authoritative transport-neutral eligibility of a validated assessment."""
    return (
        assessment.in_catalog
        and interface_state(
            assessment.local_readiness, assessment.source_path, assessment.relationships
        )
        == State.READY
    )
