"""Static output selections and explicit, read-only observations of current bytes."""

import ast
import errno
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, field_validator

from apizr.experiments._files import FileFailure, FileFailureCode, fingerprint_file
from apizr.experiments._lexical import (
    MAX_DEPTH,
    MAX_NODES,
    MAX_SOURCE_BYTES,
    LexicalVisitor,
    SourceLimit,
    bounded_tree,
)
from apizr.experiments.inputs import FingerprintPolicy
from apizr.experiments.model import (
    EvidenceOrigin,
    ExperimentValue,
    Name,
    OutputArtifact,
    Reference,
    ordered_evidence,
)

_REFERENCE = TypeAdapter[str](Reference)
OutputDiagnosticCode = Literal[
    "dynamic_output_reference",
    "nonportable_output_reference",
    "unsupported_output_arguments",
    "output_name_required",
    "output_missing",
    "output_symlink",
    "output_not_regular",
    "output_too_large",
    "output_changed_during_read",
    "output_unreadable",
    "output_source_invalid",
    "output_discovery_limit",
]


class OutputDeclaration(ExperimentValue):
    """Explicit selection or static candidate; never a content observation."""

    name: Name
    reference: Reference
    media_type: Name | None = None


class OutputSignal(ExperimentValue):
    declaration: OutputDeclaration
    callable_name: Literal["joblib.dump"] = "joblib.dump"
    source: Reference
    line: Annotated[int, Field(ge=1, le=MAX_SOURCE_BYTES)]
    column: Annotated[int, Field(ge=0, le=MAX_SOURCE_BYTES)]
    origin: Literal[EvidenceOrigin.STATIC] = EvidenceOrigin.STATIC


class OutputDiagnostic(ExperimentValue):
    code: OutputDiagnosticCode
    source: Reference | None = None
    line: Annotated[int, Field(ge=1, le=MAX_SOURCE_BYTES)] | None = None
    column: Annotated[int, Field(ge=0, le=MAX_SOURCE_BYTES)] | None = None
    name: Name | None = None


def _ordered_diagnostics(
    items: tuple[OutputDiagnostic, ...],
) -> tuple[OutputDiagnostic, ...]:
    return tuple(
        sorted(
            set(items),
            key=lambda d: (
                d.source or "",
                d.line or 0,
                d.column or 0,
                d.name or "",
                d.code,
            ),
        )
    )


class OutputDiscoveryResult(ExperimentValue):
    """Every recognized occurrence is retained separately from runtime artifacts."""

    signals: Annotated[tuple[OutputSignal, ...], Field(max_length=256)] = ()
    diagnostics: Annotated[tuple[OutputDiagnostic, ...], Field(max_length=512)] = ()
    relevant_distributions: Annotated[
        tuple[Literal["joblib"], ...], Field(max_length=1)
    ] = ()

    @field_validator("signals")
    @classmethod
    def ordered_signals(
        cls, items: tuple[OutputSignal, ...]
    ) -> tuple[OutputSignal, ...]:
        keys = [(s.source, s.line, s.column) for s in items]
        if len(keys) != len(set(keys)):
            raise ValueError("output_signal_duplicate_occurrence")
        return tuple(sorted(items, key=lambda s: (s.source, s.line, s.column)))

    _diagnostics = field_validator("diagnostics")(_ordered_diagnostics)


class OutputCaptureResult(ExperimentValue):
    artifacts: Annotated[tuple[OutputArtifact, ...], Field(max_length=256)] = ()
    diagnostics: Annotated[tuple[OutputDiagnostic, ...], Field(max_length=512)] = ()

    @field_validator("artifacts")
    @classmethod
    def ordered_artifacts(
        cls, items: tuple[OutputArtifact, ...]
    ) -> tuple[OutputArtifact, ...]:
        return ordered_evidence(items, lambda item: item.name)

    _diagnostics = field_validator("diagnostics")(_ordered_diagnostics)


def parse_output_declaration(value: object) -> OutputDeclaration:
    """Pure name=relative-reference parser, without trimming, URI resolution or I/O."""
    try:
        if not isinstance(value, str) or len(value) > 1153:
            raise ValueError
        name, separator, reference = value.partition("=")
        if not separator:
            raise ValueError
        return OutputDeclaration(name=name, reference=reference)
    except (ValueError, UnicodeError):
        raise ValueError("explicit_output_invalid") from None


def _capture(
    root: Path, selection: OutputDeclaration, policy: FingerprintPolicy
) -> OutputCaptureResult:
    code: OutputDiagnosticCode
    try:
        digest, size = fingerprint_file(
            root, selection.reference, policy.max_file_bytes
        )
        return OutputCaptureResult(
            artifacts=(
                OutputArtifact(
                    name=selection.name,
                    reference=selection.reference,
                    digest=digest,
                    size=size,
                    media_type=selection.media_type,
                    origin=EvidenceOrigin.RUNTIME,
                ),
            )
        )
    except FileFailure as error:
        failures: dict[FileFailureCode, OutputDiagnosticCode] = {
            "symlink": "output_symlink",
            "not_regular": "output_not_regular",
            "too_large": "output_too_large",
            "changed_during_read": "output_changed_during_read",
        }
        code = failures[error.code]
    except OSError as error:
        errors: dict[int | None, OutputDiagnosticCode] = {
            errno.ENOENT: "output_missing",
            errno.ELOOP: "output_symlink",
            errno.ENOTDIR: "output_not_regular",
        }
        code = errors.get(error.errno, "output_unreadable")
    return OutputCaptureResult(
        diagnostics=(OutputDiagnostic(code=code, name=selection.name),)
    )


def fingerprint_outputs(
    root: Path,
    selections: tuple[OutputDeclaration, ...],
    *,
    policy: FingerprintPolicy | None = None,
) -> OutputCaptureResult:
    """Observe selected files after complete admission; the caller owns run lifecycle."""
    try:
        if type(selections) is not tuple or len(selections) > 256:
            raise ValueError
        admitted = ordered_evidence(
            tuple(OutputDeclaration.model_validate(item) for item in selections),
            lambda item: item.name,
        )
        policy = (
            FingerprintPolicy()
            if policy is None
            else FingerprintPolicy.model_validate(policy)
        )
    except (ValueError, UnicodeError):
        raise ValueError("output_selection_invalid") from None
    results = tuple(_capture(root, item, policy) for item in admitted)
    return OutputCaptureResult(
        artifacts=tuple(a for result in results for a in result.artifacts),
        diagnostics=tuple(d for result in results for d in result.diagnostics),
    )


def fingerprint_output(
    root: Path,
    selection: OutputDeclaration,
    *,
    policy: FingerprintPolicy | None = None,
) -> OutputCaptureResult:
    """Hash one current regular file; no execution, deserialization, copy or upload."""
    return fingerprint_outputs(root, (selection,), policy=policy)


class _Discovery(LexicalVisitor):
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
    discovery = _Discovery(source_reference)
    discovery.visit(tree)
    if len(discovery.signals) > 256 or len(discovery.diagnostics) > 512:
        return OutputDiscoveryResult(
            diagnostics=(
                OutputDiagnostic(
                    code="output_discovery_limit", source=source_reference
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
