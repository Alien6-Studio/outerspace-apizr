"""Self-contained catalog and checked indexes over existing Inspection v1."""

from enum import Enum
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from apizr.capabilities.model import Digest, ExecutionForm, Severity, SourceSpan
from apizr.capabilities.types import ValueModel
from apizr.inspection import Inspection, json_bytes
from apizr.readiness import State

from .modules import module_name, source_root
from .policy import ScanPolicy, relative_path
from .serialization import canonical_bytes, policy_digest


class Code(str, Enum):
    MODULE = "APIZR-REPO-001"
    COLLISION = "APIZR-REPO-002"
    READ = "APIZR-REPO-003"
    SIZE = "APIZR-REPO-004"
    LIMIT = "APIZR-REPO-005"
    SYMLINK = "APIZR-REPO-006"
    ROOT = "APIZR-REPO-007"
    PARSE = "APIZR-REPO-008"
    ENCODING = "APIZR-REPO-009"
    ANALYSIS = "APIZR-REPO-010"


MESSAGES = {
    Code.MODULE: "Source path cannot form a logical Python module.",
    Code.COLLISION: "Multiple sources identify the same logical module.",
    Code.READ: "Source or directory could not be safely read.",
    Code.SIZE: "Source exceeds the per-file byte limit.",
    Code.LIMIT: "Scan resource limit exceeded; inventory discarded.",
    Code.SYMLINK: "Symbolic link skipped without following its target.",
    Code.ROOT: "Source root is missing, inaccessible or a symbolic link.",
    Code.PARSE: "Python source could not be parsed; no source excerpt retained.",
    Code.ENCODING: "Python source could not be decoded.",
    Code.ANALYSIS: "Static inspection exceeded the parser recursion limit.",
}


class Diagnostic(ValueModel):
    code: Code
    path: str
    line: int | None = Field(default=None, ge=1)
    limit: Literal["sources", "bytes", "entries", "depth"] | None = None

    @field_validator("path")
    @classmethod
    def path_value(cls, value: str) -> str:
        return relative_path(value, allow_root=True)

    @property
    def severity(self) -> Severity:
        return Severity.WARNING if self.code == Code.SYMLINK else Severity.ERROR

    @property
    def message(self) -> str:
        return MESSAGES[self.code]


class SourceUnit(ValueModel):
    path: str
    source_root: str
    module: str | None
    source_digest: Digest | None
    size: int | None = Field(ge=0)
    is_package: bool
    inspection: Inspection | None = None
    inspection_digest: Digest | None = None

    @model_validator(mode="after")
    def bound(self) -> Self:
        if self.path != relative_path(self.path) or self.source_root != relative_path(
            self.source_root, allow_root=True
        ):
            raise ValueError("Source paths must be canonical")
        try:
            expected = module_name(self.path, self.source_root)
        except ValueError:
            expected = None
        if self.module != expected or self.is_package != (
            PurePosixPath(self.path).name == "__init__.py"
        ):
            raise ValueError("Source identity disagrees with its path")
        if self.source_digest is not None and self.size is None:
            raise ValueError("Hashed source must have its exact size")
        if self.inspection is None:
            if self.inspection_digest is not None:
                raise ValueError("Inspection digest without Inspection")
        elif (
            self.inspection_digest != Digest.of_bytes(json_bytes(self.inspection))
            or self.inspection.capability_ir.source.module != self.module
            or self.inspection.capability_ir.source.digest != self.source_digest
            or self.inspection.capability_ir.source.kind != "python"
        ):
            raise ValueError("Source and Inspection linkage disagree")
        return self


class CapabilityEntry(ValueModel):
    id: str
    module: str
    source_path: str
    source_digest: Digest
    ir_digest: Digest
    readiness_digest: Digest
    readiness: State
    can_generate_interface: bool
    execution: ExecutionForm
    span: SourceSpan


def capability_entries(sources: tuple[SourceUnit, ...]) -> tuple[CapabilityEntry, ...]:
    entries: list[CapabilityEntry] = []
    for source in sources:
        inspection = source.inspection
        if inspection is None:
            continue
        assessments = {a.capability_id: a for a in inspection.readiness.assessments}
        if {a.capability_id for a in assessments.values() if a.in_ir} != {
            c.id for c in inspection.capability_ir.capabilities
        }:
            raise ValueError("Inspection readiness membership must agree with IR")
        for capability in inspection.capability_ir.capabilities:
            assessment = assessments[capability.id]
            entries.append(
                CapabilityEntry(
                    id=capability.id,
                    module=capability.source.module,
                    source_path=source.path,
                    source_digest=inspection.capability_ir.source.digest,
                    ir_digest=inspection.ir_digest,
                    readiness_digest=inspection.readiness_digest,
                    readiness=assessment.state,
                    can_generate_interface=assessment.can_generate_interface,
                    execution=capability.execution,
                    span=capability.source,
                )
            )
    return tuple(sorted(entries, key=lambda e: e.id))


class InventoryEntry(ValueModel):
    path: str
    module: str | None
    source_digest: Digest | None


class Inventory(ValueModel):
    scan_policy_digest: Digest
    sources: tuple[InventoryEntry, ...]
    discovery_diagnostics: tuple[Diagnostic, ...]


def repository_digest(
    policy: ScanPolicy,
    sources: tuple[SourceUnit, ...],
    diagnostics: tuple[Diagnostic, ...],
) -> Digest:
    inventory = Inventory(
        scan_policy_digest=policy_digest(policy),
        sources=tuple(
            InventoryEntry(path=s.path, module=s.module, source_digest=s.source_digest)
            for s in sorted(sources, key=lambda s: s.path)
        ),
        discovery_diagnostics=tuple(
            d
            for d in sorted(diagnostics, key=diagnostic_key)
            if d.code not in {Code.PARSE, Code.ENCODING, Code.ANALYSIS}
        ),
    )
    return Digest.of_bytes(canonical_bytes(inventory))


def diagnostic_key(diagnostic: Diagnostic) -> tuple[str, int, str, str]:
    return (
        diagnostic.path,
        diagnostic.line or 0,
        diagnostic.code.value,
        diagnostic.limit or "",
    )


class Statistics(ValueModel):
    sources: int
    inspected_sources: int
    capabilities: int
    assessments: int
    readiness: dict[State, int]
    repository_diagnostics: dict[Severity, int]
    sources_with_diagnostics: int


class Catalog(ValueModel):
    schema_version: Literal["apizr.catalog/v1"] = "apizr.catalog/v1"
    scan_policy: ScanPolicy
    scan_policy_digest: Digest
    repository_digest: Digest
    sources: tuple[SourceUnit, ...]
    capabilities: tuple[CapabilityEntry, ...]
    diagnostics: tuple[Diagnostic, ...] = ()

    @field_validator("sources")
    @classmethod
    def sources_ordered(cls, values: tuple[SourceUnit, ...]) -> tuple[SourceUnit, ...]:
        if len({s.path for s in values}) != len(values):
            raise ValueError("Duplicate source paths")
        return tuple(sorted(values, key=lambda s: s.path))

    @field_validator("capabilities")
    @classmethod
    def capabilities_ordered(
        cls, values: tuple[CapabilityEntry, ...]
    ) -> tuple[CapabilityEntry, ...]:
        if len({c.id for c in values}) != len(values):
            raise ValueError("Duplicate capability IDs")
        return tuple(sorted(values, key=lambda c: c.id))

    @field_validator("diagnostics")
    @classmethod
    def diagnostics_ordered(
        cls, values: tuple[Diagnostic, ...]
    ) -> tuple[Diagnostic, ...]:
        return tuple(sorted(set(values), key=diagnostic_key))

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.scan_policy_digest != policy_digest(
            self.scan_policy
        ) or self.repository_digest != repository_digest(
            self.scan_policy, self.sources, self.diagnostics
        ):
            raise ValueError("Catalog content digests disagree")
        modules: dict[str, list[SourceUnit]] = {}
        for source in self.sources:
            if source.inspection is None and not any(
                d.path == source.path and d.severity == Severity.ERROR
                for d in self.diagnostics
            ):
                raise ValueError("Uninspected source requires an error diagnostic")
            if source_root(source.path, self.scan_policy) != source.source_root:
                raise ValueError("Source is outside selected policy")
            if source.module is not None:
                modules.setdefault(source.module, []).append(source)
        for group in modules.values():
            if len(group) > 1 and any(
                s.inspection is not None
                or Diagnostic(code=Code.COLLISION, path=s.path) not in self.diagnostics
                for s in group
            ):
                raise ValueError("Colliding modules cannot carry trusted inspections")
        if self.capabilities != capability_entries(self.sources):
            raise ValueError("Capability index must agree with source inspections")
        return self

    @property
    def statistics(self) -> Statistics:
        assessments = [
            a
            for s in self.sources
            if s.inspection
            for a in s.inspection.readiness.assessments
        ]
        affected = {d.path for d in self.diagnostics}
        affected.update(
            s.path
            for s in self.sources
            if s.inspection
            and (
                s.inspection.capability_ir.diagnostics
                or any(
                    a.state != State.READY for a in s.inspection.readiness.assessments
                )
            )
        )
        return Statistics(
            sources=len(self.sources),
            inspected_sources=sum(s.inspection is not None for s in self.sources),
            capabilities=len(self.capabilities),
            assessments=len(assessments),
            readiness={
                state: sum(a.state == state for a in assessments) for state in State
            },
            repository_diagnostics={
                severity: sum(d.severity == severity for d in self.diagnostics)
                for severity in Severity
            },
            sources_with_diagnostics=sum(s.path in affected for s in self.sources),
        )

    @property
    def exit_code(self) -> int:
        return int(
            any(d.severity == Severity.ERROR for d in self.diagnostics)
            or any(
                s.inspection
                and (
                    any(
                        d.severity == Severity.ERROR
                        for d in s.inspection.capability_ir.diagnostics
                    )
                    or any(
                        a.state == State.AMBIGUOUS
                        for a in s.inspection.readiness.assessments
                    )
                )
                for s in self.sources
            )
        )
