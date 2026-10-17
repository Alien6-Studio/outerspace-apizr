"""Immutable policy facts reused within one matching-source assessment."""

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from apizr.capabilities.instrumentation import TrackingBindings
from apizr.capabilities.model import Capability

from .contracts import classify
from .model import Code, Reason, StructuredDeclaration
from .source import SourceFacts, initialization_risk


@dataclass(frozen=True, slots=True)
class ReadinessAnalysis:
    initialization: tuple[Reason, ...]
    annotations: Mapping[tuple[str | None, int], tuple[Code, ...]]
    declaration_lines: tuple[int, ...]

    def codes(self, declared: str | None, line: int) -> tuple[Code, ...]:
        boundary = sum(declaration < line for declaration in self.declaration_lines)
        return self.annotations[declared, boundary]


def analyze(
    capabilities: tuple[Capability, ...],
    facts: SourceFacts,
    stubs: set[int],
    declarations: tuple[StructuredDeclaration, ...],
    tracking: TrackingBindings,
    module: str,
) -> ReadinessAnalysis:
    """Discard parsed annotation expressions after classification; retain no AST."""
    safe_classes = {d.source.line for d in declarations if d.type is not None}
    initialization = tuple(
        Reason(code=Code.INITIALIZATION, line=statement.lineno)
        for statement in facts.tree.body
        if statement.lineno not in stubs | safe_classes
        and initialization_risk(statement, tracking=tracking)
        and not facts.import_only_main_guard(statement, module)
    )
    lines = tuple(d.source.line for d in declarations)
    annotations: dict[tuple[str | None, int], tuple[Code, ...]] = {}
    for capability in capabilities:
        line = capability.source.line
        boundary = sum(declaration < line for declaration in lines)
        shapes = {
            d.name: d.type if d.source.line < line else None for d in declarations
        }
        signatures = (
            capability.signature,
            *(o.signature for o in capability.overloads),
        )
        types = [p.annotation for s in signatures for p in s.parameters]
        types.append(capability.signature.returns.annotation)
        for annotation in types:
            declared = annotation.declared if annotation else None
            key = declared, boundary
            if key not in annotations:
                annotations[key] = classify(
                    ast.parse(declared, mode="eval").body if declared else None,
                    facts,
                    shapes,
                )
    return ReadinessAnalysis(initialization, MappingProxyType(annotations), lines)
