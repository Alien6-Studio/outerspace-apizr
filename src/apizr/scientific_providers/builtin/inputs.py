"""Built-in inputs recognition; source syntax only, never scientific imports."""

import ast

from pydantic import TypeAdapter

from apizr.experiments.inputs import DiagnosticCode, InputDiagnostic, InputResult
from apizr.experiments.model import (
    EvidenceOrigin,
    FormatHint,
    InputArtifact,
    Reference,
    RemoteURI,
)
from apizr.experiments.provider_source import MAX_DEPTH as _MAX_DEPTH
from apizr.experiments.provider_source import MAX_NODES as _MAX_NODES
from apizr.experiments.provider_source import MAX_SOURCE_BYTES as _MAX_SOURCE_BYTES
from apizr.experiments.provider_source import (
    SourceLexicalVisitor,
    SourceLimit,
    bounded_tree,
)

_LOADERS: dict[str, FormatHint] = {
    "pandas.read_csv": "csv",
    "pandas.read_parquet": "parquet",
    "numpy.load": "numpy",
    "joblib.load": "joblib",
}

_REFERENCE = TypeAdapter[str](Reference)


class Discovery(SourceLexicalVisitor):
    def __init__(self, source: str) -> None:
        super().__init__(
            frozenset({"pandas", "numpy", "joblib"}).__contains__, _LOADERS.__contains__
        )
        self.source = source
        self.artifacts: dict[str, InputArtifact] = {}
        self.diagnostics: list[InputDiagnostic] = []

    def diagnostic(
        self, code: DiagnosticCode, node: ast.expr, loader: str | None = None
    ) -> None:
        self.diagnostics.append(
            InputDiagnostic.model_validate(
                {
                    "code": code,
                    "source": self.source,
                    "line": node.lineno,
                    "column": node.col_offset,
                    "loader": loader,
                }
            )
        )

    def visit_Call(self, node: ast.Call) -> None:
        qualified = self.resolve_call(node)
        if qualified in _LOADERS:
            self.input_call(node, qualified)
        elif isinstance(node.func, ast.Call):
            self.diagnostic("unsupported_input_reference", node)
        self.generic_visit(node)

    def input_call(self, node: ast.Call, loader: str) -> None:
        if (
            not node.args
            or not isinstance(node.args[0], ast.Constant)
            or not isinstance(node.args[0].value, str)
        ):
            self.diagnostic("dynamic_input_reference", node, loader)
            return
        literal = node.args[0].value
        remote = "://" in literal
        try:
            artifact = InputArtifact.model_validate(
                {
                    "name": literal,
                    "uri" if remote else "reference": literal,
                    "origin": EvidenceOrigin.STATIC,
                    "content_origin": EvidenceOrigin.UNKNOWN,
                    "format_hint": _LOADERS[loader],
                }
            )
        except (ValueError, UnicodeError):
            code: DiagnosticCode = (
                "unsupported_input_reference"
                if remote
                else "nonportable_input_reference"
            )
            # Validate reference separately: a portable but long reference needs
            # an explicit short name, never a truncated synthetic identity.
            try:
                (TypeAdapter[str](RemoteURI) if remote else _REFERENCE).validate_python(
                    literal, strict=True
                )
                code = "input_name_required"
            except (ValueError, UnicodeError):
                pass
            self.diagnostic(code, node, loader)
            return
        previous = self.artifacts.get(artifact.name)
        if previous is not None and previous.format_hint != artifact.format_hint:
            artifact = artifact.model_copy(update={"format_hint": None})
            self.diagnostic("input_format_conflict", node, loader)
        self.artifacts[artifact.name] = artifact
        if remote:
            self.diagnostic("remote_content_unverified", node, loader)


def discover_inputs(source: str | bytes, *, source_reference: str) -> InputResult:
    """Parse supplied Python only. Literal first positional loader arguments only."""
    try:
        _REFERENCE.validate_python(source_reference, strict=True)
        tree = bounded_tree(
            source,
            max_bytes=_MAX_SOURCE_BYTES,
            max_nodes=_MAX_NODES,
            max_depth=_MAX_DEPTH,
        )
    except SourceLimit as error:
        return InputResult(
            diagnostics=(
                InputDiagnostic(
                    code="input_discovery_limit",
                    source=source_reference if error.parsed else None,
                ),
            )
        )
    except (ValueError, UnicodeError, SyntaxError, RecursionError):
        return InputResult(diagnostics=(InputDiagnostic(code="input_source_invalid"),))
    discovery = Discovery(source_reference)
    discovery.visit(tree)
    return discovery_result(discovery)


def discovery_result(discovery: Discovery) -> InputResult:
    if len(discovery.artifacts) > 256 or len(discovery.diagnostics) > 512:
        return InputResult(
            diagnostics=(
                InputDiagnostic(code="input_discovery_limit", source=discovery.source),
            )
        )
    return InputResult(
        artifacts=tuple(discovery.artifacts.values()),
        diagnostics=tuple(discovery.diagnostics),
    )
