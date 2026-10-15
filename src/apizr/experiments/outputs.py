"""Static output selections and explicit, read-only observations of current bytes."""

import errno
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator

from apizr.experiments._files import FileFailure, FileFailureCode, fingerprint_file
from apizr.experiments._lexical import MAX_SOURCE_BYTES as MAX_SOURCE_BYTES
from apizr.experiments.inputs import FingerprintPolicy
from apizr.experiments.model import (
    EvidenceOrigin,
    ExperimentValue,
    Name,
    OutputArtifact,
    Reference,
    ordered_evidence,
)

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


def discover_outputs(
    source: str | bytes, *, source_reference: str
) -> OutputDiscoveryResult:
    """Dispatch to the official built-in recognizer, installed with the core."""
    from apizr.scientific_providers.builtin.outputs import discover_outputs as recognize

    return recognize(source, source_reference=source_reference)
