"""Source-only input discovery and explicit, bounded local byte observations."""

import ast
import errno
import hashlib
import os
import stat
from contextlib import ExitStack
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import (
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from apizr.experiments._lexical import (
    MAX_DEPTH as _MAX_DEPTH,
)
from apizr.experiments._lexical import (
    MAX_NODES as _MAX_NODES,
)
from apizr.experiments._lexical import (
    MAX_SOURCE_BYTES as _MAX_SOURCE_BYTES,
)
from apizr.experiments._lexical import (
    LexicalVisitor,
    SourceLimit,
    bounded_tree,
)
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
from apizr.workspace.files import directory_fd

_LOADERS: dict[str, FormatHint] = {
    "pandas.read_csv": "csv",
    "pandas.read_parquet": "parquet",
    "numpy.load": "numpy",
    "joblib.load": "joblib",
}
_SUFFIXES: dict[str, FormatHint] = {
    ".csv": "csv",
    ".parquet": "parquet",
    ".npy": "numpy",
    ".npz": "numpy",
    ".joblib": "joblib",
}
_REFERENCE = TypeAdapter[str](Reference)
_CHUNK_BYTES = 1024 * 1024


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


class _Discovery(LexicalVisitor):
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
    discovery = _Discovery(source_reference)
    discovery.visit(tree)
    if len(discovery.artifacts) > 256 or len(discovery.diagnostics) > 512:
        return InputResult(
            diagnostics=(
                InputDiagnostic(code="input_discovery_limit", source=source_reference),
            )
        )
    return InputResult(
        artifacts=tuple(discovery.artifacts.values()),
        diagnostics=tuple(discovery.diagnostics),
    )


class _InputFailure(Exception):
    def __init__(self, code: DiagnosticCode):
        self.code: DiagnosticCode = code


def _snapshot(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _regular_digest(root: Path, reference: str, limit: int) -> tuple[str, int]:
    with ExitStack() as stack:
        parent = stack.enter_context(directory_fd(root))
        parts = reference.split("/")
        for index, part in enumerate(parts):
            info = os.stat(part, dir_fd=parent, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                raise _InputFailure("input_symlink")
            if index < len(parts) - 1:
                if not stat.S_ISDIR(info.st_mode):
                    raise _InputFailure("input_not_regular")
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
                )
                stack.callback(os.close, child)
                parent = child
            elif not stat.S_ISREG(info.st_mode):
                raise _InputFailure("input_not_regular")
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
        stack.callback(os.close, descriptor)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise _InputFailure("input_not_regular")
        if before.st_size > limit:
            raise _InputFailure("input_too_large")
        digest = hashlib.sha256()
        size = 0
        while chunk := os.read(descriptor, min(_CHUNK_BYTES, limit - size + 1)):
            size += len(chunk)
            if size > limit:
                raise _InputFailure("input_too_large")
            digest.update(chunk)
        after = os.fstat(descriptor)
        try:
            current = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        except OSError:
            current = None
        if (
            _snapshot(before) != _snapshot(after)
            or current is None
            or _snapshot(after) != _snapshot(current)
            or size != before.st_size
        ):
            raise _InputFailure("input_changed_during_read")
        return digest.hexdigest(), size


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
            digest, size = _regular_digest(
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
        except _InputFailure as error:
            code = error.code
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
