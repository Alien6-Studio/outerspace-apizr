"""Apply bounded readiness policy to IR and matching source evidence."""

import ast
import io
import tokenize
from collections import defaultdict

from apizr.capabilities import CapabilityDocument, document_digest, inspect_source
from apizr.capabilities.model import Capability, DiagnosticCode, Effects, SourceSpan

from .contracts import classify
from .model import (
    Assessment,
    Code,
    Dimension,
    Dimensions,
    ReadinessReport,
    Reason,
    State,
)
from .source import SourceFacts, initialization_risk, unresolved_import


def _reasons(
    codes: tuple[Code, ...], line: int, parameter: str | None = None
) -> tuple[Reason, ...]:
    return tuple(Reason(code=code, line=line, parameter=parameter) for code in codes)


def _assessment(
    source: SourceSpan, dimensions: Dimensions, *, capability: Capability | None
) -> Assessment:
    return Assessment(
        capability_id=f"python:{source.module}:{source.symbol}",
        source=source,
        in_ir=capability is not None,
        effects=capability.effects if capability else Effects(),
        dimensions=dimensions,
        state=dimensions.state,
        can_generate_interface=capability is not None
        and dimensions.state == State.READY,
    )


def _capability(
    capability: Capability, facts: SourceFacts, stub_lines: set[int]
) -> Assessment:
    source = capability.source
    function = facts.functions[source.symbol, source.line]
    order = facts.function_orders[source.symbol, source.line]
    binding: list[Reason] = []
    execution: list[Reason] = []
    if capability.availability.value == "unknown" and function not in facts.tree.body:
        binding.extend(_reasons((Code.CONDITIONAL,), source.line))
    if capability.decorators:
        binding.extend(_reasons((Code.DECORATOR,), source.line))
    for event in facts.bindings[source.symbol]:
        if event.order > order:
            binding.extend(_reasons((Code.REBOUND,), event.line))
    for line in facts.namespace_lines:
        binding.extend(_reasons((Code.NAMESPACE,), line))
    for statement in facts.tree.body:
        if statement.lineno not in stub_lines and initialization_risk(statement):
            execution.extend(_reasons((Code.INITIALIZATION,), statement.lineno))
    if capability.execution == "generator":
        execution.extend(_reasons((Code.GENERATOR,), source.line))
    elif capability.execution == "async_generator":
        execution.extend(_reasons((Code.ASYNC_GENERATOR,), source.line))
    for line in facts.dynamic_import_lines((*facts.calls, function)):
        execution.extend(_reasons((Code.DYNAMIC_IMPORT,), line))
    imports = facts.imports + [
        n for n in ast.walk(function) if isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    for imported in imports:
        if unresolved_import(imported):
            execution.extend(_reasons((Code.DEPENDENCY,), imported.lineno))
    signatures = [(capability.signature, source.line)] + [
        (o.signature, o.source.line) for o in capability.overloads
    ]
    inputs = tuple(
        reason
        for signature, line in signatures
        for parameter in signature.parameters
        for reason in _reasons(
            classify(
                ast.parse(parameter.annotation.declared, mode="eval").body
                if parameter.annotation
                else None,
                facts,
            ),
            line,
            parameter.name,
        )
    )
    output_type = capability.signature.returns.annotation
    output_codes = classify(
        ast.parse(output_type.declared, mode="eval").body if output_type else None,
        facts,
    )
    output = _reasons((Code.OUTPUT,), source.line) if output_codes else ()
    return _assessment(
        source,
        Dimensions(
            binding=Dimension.assess(tuple(binding)),
            execution=Dimension.assess(tuple(execution)),
            inputs=Dimension.assess(inputs),
            outputs=Dimension.assess(output),
        ),
        capability=capability,
    )


def assess(document: CapabilityDocument, source: str | bytes) -> ReadinessReport:
    """Assess only matching source; for notebooks source is exported Python text."""
    checked = inspect_source(source, module_name=document.source.module)
    expected_digest = document.source.transformed_digest or document.source.digest
    if checked.source.digest != expected_digest:
        raise ValueError("Readiness source digest does not match Capability IR")
    if (
        checked.capabilities != document.capabilities
        or checked.diagnostics != document.diagnostics
    ):
        raise ValueError("Readiness source declarations do not match Capability IR")
    if isinstance(source, bytes):
        encoding, _ = tokenize.detect_encoding(io.BytesIO(source).readline)
        source = source.decode(encoding)
    facts = SourceFacts(ast.parse(source, filename="<readiness-source>"))
    stubs = {o.source.line for c in document.capabilities for o in c.overloads}
    assessments = [_capability(c, facts, stubs) for c in document.capabilities]
    present = {c.name for c in document.capabilities}
    rejected: dict[str, list[Reason]] = defaultdict(list)
    spans: dict[str, SourceSpan] = {}
    codes = {
        DiagnosticCode.DUPLICATE: Code.DUPLICATE,
        DiagnosticCode.OVERLOAD: Code.OVERLOAD,
        DiagnosticCode.VARIADIC: Code.VARIADIC,
        DiagnosticCode.BINDING: Code.CONSTRUCT,
    }
    for diagnostic in document.diagnostics:
        symbol = diagnostic.source.symbol
        if symbol not in present and diagnostic.code in codes:
            spans[symbol] = diagnostic.source
            rejected[symbol].extend(
                _reasons((codes[diagnostic.code],), diagnostic.source.line)
            )
    for symbol, reasons in rejected.items():
        dimensions = Dimensions(
            binding=Dimension.assess(
                tuple(r for r in reasons if r.code in {Code.DUPLICATE, Code.OVERLOAD})
            ),
            inputs=Dimension.assess(
                tuple(r for r in reasons if r.code == Code.VARIADIC)
            ),
            execution=Dimension.assess(
                tuple(r for r in reasons if r.code == Code.CONSTRUCT)
            ),
            outputs=Dimension.assess(),
        )
        assessments.append(_assessment(spans[symbol], dimensions, capability=None))
    return ReadinessReport(
        source=document.source,
        ir_digest=document_digest(document),
        assessments=tuple(assessments),
    )
