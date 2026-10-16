"""Built-in outputs recognition; source syntax only, never scientific imports."""

import ast

from pydantic import TypeAdapter

from apizr.experiments.model import Reference
from apizr.experiments.outputs import (
    OutputDeclaration,
    OutputDiagnostic,
    OutputDiagnosticCode,
    OutputDiscoveryResult,
    OutputSignal,
)
from apizr.experiments.provider_source import (
    MAX_DEPTH,
    MAX_NODES,
    MAX_SOURCE_BYTES,
    SourceLexicalVisitor,
    SourceLimit,
    bounded_tree,
)

_REFERENCE = TypeAdapter[str](Reference)


class Discovery(SourceLexicalVisitor):
    def __init__(self, source: str) -> None:
        super().__init__(
            lambda name: name == "joblib", lambda name: name == "joblib.dump"
        )
        self.source = source
        self.signals: list[OutputSignal] = []
        self.diagnostics: list[OutputDiagnostic] = []

    def diagnostic(self, code: OutputDiagnosticCode, node: ast.Call) -> None:
        self.diagnostics.append(
            OutputDiagnostic(
                code=code, source=self.source, line=node.lineno, column=node.col_offset
            )
        )

    def visit_Call(self, node: ast.Call) -> None:
        if self.resolve_call(node) == "joblib.dump":
            self.output_call(node)
        self.generic_visit(node)

    def output_call(self, node: ast.Call) -> None:
        parameters = ("value", "filename", "compress", "protocol")
        keywords = {k.arg: k.value for k in node.keywords}
        if (
            len(node.args) > 4
            or any(isinstance(arg, ast.Starred) for arg in node.args)
            or len(keywords) != len(node.keywords)
            or any(
                key not in parameters or key in parameters[: len(node.args)]
                for key in keywords
            )
            or (not node.args and "value" not in keywords)
        ):
            self.diagnostic("unsupported_output_arguments", node)
            return
        expression = node.args[1] if len(node.args) >= 2 else keywords.get("filename")
        if expression is None:
            self.diagnostic("unsupported_output_arguments", node)
            return
        if not isinstance(expression, ast.Constant) or not isinstance(
            expression.value, str
        ):
            self.diagnostic("dynamic_output_reference", node)
            return
        try:
            reference = _REFERENCE.validate_python(expression.value, strict=True)
        except (ValueError, UnicodeError):
            self.diagnostic("nonportable_output_reference", node)
            return
        try:
            declaration = OutputDeclaration(name=reference, reference=reference)
        except (ValueError, UnicodeError):
            self.diagnostic("output_name_required", node)
            return
        self.signals.append(
            OutputSignal(
                declaration=declaration,
                source=self.source,
                line=node.lineno,
                column=node.col_offset,
            )
        )


def discover_outputs(
    source: str | bytes, *, source_reference: str
) -> OutputDiscoveryResult:
    """Recognize joblib.dump literal filename arguments, without observing any file."""
    try:
        _REFERENCE.validate_python(source_reference, strict=True)
        tree = bounded_tree(
            source, max_bytes=MAX_SOURCE_BYTES, max_nodes=MAX_NODES, max_depth=MAX_DEPTH
        )
    except SourceLimit as error:
        return OutputDiscoveryResult(
            diagnostics=(
                OutputDiagnostic(
                    code="output_discovery_limit",
                    source=source_reference if error.parsed else None,
                ),
            )
        )
    except (ValueError, UnicodeError, SyntaxError, RecursionError, TypeError):
        return OutputDiscoveryResult(
            diagnostics=(OutputDiagnostic(code="output_source_invalid"),)
        )
    discovery = Discovery(source_reference)
    discovery.visit(tree)
    return discovery_result(discovery)


def discovery_result(discovery: Discovery) -> OutputDiscoveryResult:
    if len(discovery.signals) > 256 or len(discovery.diagnostics) > 512:
        return OutputDiscoveryResult(
            diagnostics=(
                OutputDiagnostic(
                    code="output_discovery_limit", source=discovery.source
                ),
            )
        )
    return OutputDiscoveryResult(
        signals=tuple(discovery.signals),
        diagnostics=tuple(discovery.diagnostics),
        relevant_distributions=("joblib",)
        if discovery.signals or discovery.diagnostics
        else (),
    )
