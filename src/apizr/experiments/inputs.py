"""Source-only input discovery and explicit, bounded local byte observations."""

import errno
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import (
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from apizr.experiments._files import FileFailure, FileFailureCode, fingerprint_file
from apizr.experiments._lexical import MAX_SOURCE_BYTES as _MAX_SOURCE_BYTES
from apizr.experiments.model import (
    EvidenceOrigin,
    ExperimentValue,
    FormatHint,
    InputArtifact,
    Name,
    Reference,
    RemoteURI,
    ordered_evidence,
)

_SUFFIXES: dict[str, FormatHint] = {
    ".csv": "csv",
    ".parquet": "parquet",
    ".npy": "numpy",
    ".npz": "numpy",
    ".joblib": "joblib",
}


class InputDeclaration(ExperimentValue):
    """Producer selection only; cannot assert a digest or content observation."""

    name: Name
    reference: Reference | None = None
    uri: RemoteURI | None = None

    @model_validator(mode="after")
    def one_reference(self) -> Self:
        if (self.reference is None) == (self.uri is None):
            raise ValueError("explicit_input_invalid")
        return self


class FingerprintPolicy(ExperimentValue):
    """One GiB per file by default; hard maximum one TiB; at most 256 files."""

    max_file_bytes: Annotated[int, Field(ge=1, le=1024**4)] = 1024**3


DiagnosticCode = Literal[
    "dynamic_input_reference",
    "unsupported_input_reference",
    "nonportable_input_reference",
    "input_missing",
    "input_symlink",
    "input_not_regular",
    "input_too_large",
    "input_changed_during_read",
    "remote_content_unverified",
    "explicit_input_invalid",
    "input_unreadable",
    "input_format_conflict",
    "input_name_required",
    "input_discovery_limit",
    "input_source_invalid",
]


class InputDiagnostic(ExperimentValue):
    code: DiagnosticCode
    source: Reference | None = None
    line: Annotated[int, Field(ge=1, le=_MAX_SOURCE_BYTES)] | None = None
    column: Annotated[int, Field(ge=0, le=_MAX_SOURCE_BYTES)] | None = None
    loader: (
        Literal["pandas.read_csv", "pandas.read_parquet", "numpy.load", "joblib.load"]
        | None
    ) = None
    name: Name | None = None


class InputResult(ExperimentValue):
    """Candidates or selected observations, never an implicit Experiment Plan."""

    artifacts: Annotated[tuple[InputArtifact, ...], Field(max_length=256)] = ()
    diagnostics: Annotated[tuple[InputDiagnostic, ...], Field(max_length=512)] = ()

    @field_validator("artifacts")
    @classmethod
    def ordered_artifacts(
        cls, items: tuple[InputArtifact, ...]
    ) -> tuple[InputArtifact, ...]:
        return ordered_evidence(items, lambda item: item.name)

    @field_validator("diagnostics")
    @classmethod
    def ordered_diagnostics(
        cls, items: tuple[InputDiagnostic, ...]
    ) -> tuple[InputDiagnostic, ...]:
        return tuple(
            sorted(
                set(items),
                key=lambda item: (
                    item.source or "",
                    item.line or 0,
                    item.column or 0,
                    item.loader or "",
                    item.name or "",
                    item.code,
                ),
            )
        )


def parse_input_declaration(value: object) -> InputDeclaration:
    """Parse future --input name=reference syntax, without I/O or trimming."""
    try:
        if not isinstance(value, str) or len(value) > 1153:
            raise ValueError
        name, separator, reference = value.partition("=")
        if not separator:
            raise ValueError
        if "://" in reference:
            return InputDeclaration(name=name, uri=reference)
        return InputDeclaration(name=name, reference=reference)
    except (ValueError, UnicodeError):
        # Pydantic errors can echo the rejected value, including an absolute path.
        raise ValueError("explicit_input_invalid") from None


def _hint(reference: str) -> FormatHint | None:
    return _SUFFIXES.get(PurePosixPath(reference).suffix)


def _declared(declaration: InputDeclaration) -> InputArtifact:
    declaration = InputDeclaration.model_validate(declaration)
    return InputArtifact(
        name=declaration.name,
        reference=declaration.reference,
        uri=declaration.uri,
        origin=EvidenceOrigin.DECLARED,
        content_origin=EvidenceOrigin.UNKNOWN,
        format_hint=_hint(declaration.reference or declaration.uri or ""),
    )


def select_inputs(
    discovery: InputResult, declarations: tuple[InputDeclaration, ...] = ()
) -> InputResult:
    """Prefer explicit names/origins for matching references; retain uncertainty."""
    discovery = InputResult.model_validate(discovery)
    if len(declarations) > 256:
        raise ValueError("explicit_input_invalid")
    declared = tuple(_declared(item) for item in declarations)
    targets = {(item.reference, item.uri) for item in declared}
    retained = tuple(
        item
        for item in discovery.artifacts
        if (item.reference, item.uri) not in targets
    )
    try:
        return InputResult(
            artifacts=(*retained, *declared), diagnostics=discovery.diagnostics
        )
    except ValidationError:
        raise ValueError("explicit_input_invalid") from None


def fingerprint_input(
    root: Path,
    selection: InputDeclaration | InputArtifact,
    *,
    policy: FingerprintPolicy | None = None,
) -> InputResult:
    """Read exactly one selected local regular file; remote references stay unknown."""
    policy = (
        FingerprintPolicy()
        if policy is None
        else FingerprintPolicy.model_validate(policy)
    )
    artifact = (
        _declared(selection)
        if isinstance(selection, InputDeclaration)
        else InputArtifact.model_validate(selection)
    )
    if artifact.origin not in {EvidenceOrigin.DECLARED, EvidenceOrigin.STATIC}:
        raise ValueError("explicit_input_invalid")
    # Never reuse supplied hash/size claims. A fresh observation must read bytes.
    artifact = artifact.model_copy(
        update={"digest": None, "size": None, "content_origin": EvidenceOrigin.UNKNOWN}
    )
    code: DiagnosticCode
    if artifact.uri is not None:
        code = "remote_content_unverified"
    elif artifact.reference is None:
        code = "unsupported_input_reference"
    else:
        try:
            digest, size = fingerprint_file(
                root, artifact.reference, policy.max_file_bytes
            )
            return InputResult(
                artifacts=(
                    artifact.model_copy(
                        update={
                            "digest": digest,
                            "size": size,
                            "content_origin": EvidenceOrigin.STATIC,
                        }
                    ),
                )
            )
        except FileFailure as error:
            failures: dict[FileFailureCode, DiagnosticCode] = {
                "symlink": "input_symlink",
                "not_regular": "input_not_regular",
                "too_large": "input_too_large",
                "changed_during_read": "input_changed_during_read",
            }
            code = failures[error.code]
        except OSError as error:
            errors: dict[int | None, DiagnosticCode] = {
                errno.ENOENT: "input_missing",
                errno.ELOOP: "input_symlink",
                errno.ENOTDIR: "input_not_regular",
            }
            code = errors.get(error.errno, "input_unreadable")
    return InputResult(
        artifacts=(artifact,),
        diagnostics=(InputDiagnostic(code=code, name=artifact.name),),
    )


def fingerprint_inputs(
    root: Path,
    selections: tuple[InputDeclaration | InputArtifact, ...],
    *,
    policy: FingerprintPolicy | None = None,
) -> InputResult:
    """Bounded explicit batch; validate names/count/policy before any dataset I/O."""
    if len(selections) > 256:
        raise ValueError("explicit_input_invalid")
    artifacts = tuple(
        _declared(item)
        if isinstance(item, InputDeclaration)
        else InputArtifact.model_validate(item)
        for item in selections
    )
    admitted = InputResult(artifacts=artifacts)
    if any(
        item.origin not in {EvidenceOrigin.DECLARED, EvidenceOrigin.STATIC}
        for item in artifacts
    ):
        raise ValueError("explicit_input_invalid")
    policy = (
        FingerprintPolicy()
        if policy is None
        else FingerprintPolicy.model_validate(policy)
    )
    results = tuple(
        fingerprint_input(root, item, policy=policy) for item in admitted.artifacts
    )
    return InputResult(
        artifacts=tuple(item for result in results for item in result.artifacts),
        diagnostics=tuple(item for result in results for item in result.diagnostics),
    )


def discover_inputs(source: str | bytes, *, source_reference: str) -> InputResult:
    """Dispatch to the official built-in recognizer, installed with the core."""
    from apizr.scientific_providers.builtin.inputs import discover_inputs as recognize

    return recognize(source, source_reference=source_reference)
