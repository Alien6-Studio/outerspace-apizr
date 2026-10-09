"""Bounded evidence views, never partial canonical repository artifacts."""

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel, logical_module
from apizr.exposure.planner import Diagnostic
from apizr.exposure.policy import capability_id as checked_capability_id
from apizr.graph.model import ImportDeclaration, ModuleNode, Node, Relationship
from apizr.readiness.model import Assessment, State
from apizr.repository.model import CapabilityEntry
from apizr.repository.policy import relative_path
from apizr.repository_readiness.execution import ModeCompatibility
from apizr.repository_readiness.model import Reason

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_BLOCKERS = 10
Action = Literal[
    "inspect_dependency",
    "fix_import",
    "fix_binding",
    "fix_initialization",
    "select_known_capability",
    "resolve_interface_contract",
    "adjust_execution_requirements",
]


class ViewModel(ValueModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, revalidate_instances="always"
    )


class ViewQuery(ViewModel):
    view: Literal["full", "summary", "detail"] = "full"
    capability_id: str | None = Field(default=None, min_length=1, max_length=1024)
    module: str | None = Field(default=None, min_length=1, max_length=512)
    offset: int | None = Field(default=None, ge=0, le=2147483647)
    limit: int | None = Field(default=None, ge=1, le=MAX_LIMIT)
    expected_repository_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )

    @field_validator("capability_id")
    @classmethod
    def capability(cls, value: str | None) -> str | None:
        return None if value is None else checked_capability_id(value)

    @field_validator("module")
    @classmethod
    def logical(cls, value: str | None) -> str | None:
        return None if value is None else logical_module(value)

    @model_validator(mode="after")
    def combination(self) -> Self:
        filters = int(self.capability_id is not None) + int(self.module is not None)
        if self.view == "detail":
            if filters != 1:
                raise ValueError("Detail requires exactly one exact identity")
            if self.offset and self.expected_repository_digest is None:
                raise ValueError("Continuation requires the repository digest")
        elif filters or self.offset is not None or self.limit is not None:
            raise ValueError("Filters and pagination belong only to detail")
        return self


class AnalysisIdentity(ViewModel):
    repository_digest: Digest
    catalog_digest: Digest
    graph_digest: Digest


class ReadinessIdentity(AnalysisIdentity):
    repository_readiness_digest: Digest
    readiness_policy_digest: Digest


class Page(ViewModel):
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=MAX_LIMIT)
    total: int = Field(ge=0)
    returned: int = Field(ge=0)
    next_offset: int | None = Field(default=None, ge=1)
    complete: bool

    @model_validator(mode="after")
    def consistent(self) -> Self:
        expected = min(self.limit, max(0, self.total - self.offset))
        more = self.offset + expected < self.total
        if (
            self.returned != expected
            or self.complete == more
            or self.next_offset != (self.offset + expected if more else None)
        ):
            raise ValueError("Pagination metadata disagrees with the collection")
        return self


class EvidenceDiagnostic(ViewModel):
    origin: Literal["catalog", "graph", "readiness", "scope"]
    code: str = Field(min_length=1, max_length=128)
    capability_id: str | None = None
    source_path: str | None = None
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=0)
    dependency_path: tuple[str, ...] = ()
    reason: str | None = None
    action: Action | None = None

    @field_validator("source_path")
    @classmethod
    def path(cls, value: str | None) -> str | None:
        return None if value is None else relative_path(value, allow_root=True)


class Blockers(ViewModel):
    total: int = Field(ge=0)
    shown: tuple[EvidenceDiagnostic, ...] = Field(max_length=MAX_BLOCKERS)
    has_more: bool

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if len(self.shown) != min(self.total, MAX_BLOCKERS) or self.has_more != (
            self.total > len(self.shown)
        ):
            raise ValueError("Blocker sample must expose its complete count")
        return self


class AnalysisCounts(ViewModel):
    sources: int
    inspected_sources: int
    capabilities: int
    modules: int
    relationships: int
    imports: int
    graph_complete: bool
    catalog_diagnostics: int
    graph_diagnostics: int


class AnalysisSummary(ViewModel):
    view: Literal["summary"] = "summary"
    identity: AnalysisIdentity
    summary: AnalysisCounts
    principal_blockers: Blockers


class ReadinessSummary(ViewModel):
    view: Literal["summary"] = "summary"
    identity: ReadinessIdentity
    exit_code: Literal[0, 1]
    states: dict[State, int]
    execution: tuple[ModeCompatibility, ...]
    principal_blockers: Blockers


class SourceView(ViewModel):
    path: str
    module: str | None
    source_digest: Digest | None
    size: int | None
    inspected: bool
    is_package: bool

    _path = field_validator("path")(relative_path)


class CapabilityFocus(ViewModel):
    kind: Literal["capability"] = "capability"
    capability_id: str
    module: str
    source_path: str
    capability: CapabilityEntry | None
    local_readiness: Assessment
    repository_state: State
    selected_state: State
    interface_eligible: bool
    global_evidence_complete: bool
    reasons: tuple[Reason, ...]


class ModuleFocus(ViewModel):
    kind: Literal["module"] = "module"
    module: str
    source_count: int
    source: SourceView | None
    node: ModuleNode | None
    capability_count: int
    states: dict[State, int]


Focus = Annotated[CapabilityFocus | ModuleFocus, Field(discriminator="kind")]


class DependencyRecord(ViewModel):
    kind: Literal["dependency"] = "dependency"
    id: str
    node: Node | None
    exposed: Literal[False] = False


class CapabilityRecord(ViewModel):
    kind: Literal["capability"] = "capability"
    capability_id: str
    source_path: str
    capability: CapabilityEntry | None
    local_state: State
    state: State


class SourceRecord(ViewModel):
    kind: Literal["source"] = "source"
    source: SourceView


class RelationshipRecord(ViewModel):
    kind: Literal["relationship"] = "relationship"
    relationship: Relationship


class ImportRecord(ViewModel):
    kind: Literal["import"] = "import"
    declaration: ImportDeclaration


class DiagnosticRecord(ViewModel):
    kind: Literal["diagnostic"] = "diagnostic"
    diagnostic: EvidenceDiagnostic


Record = Annotated[
    DependencyRecord
    | CapabilityRecord
    | SourceRecord
    | RelationshipRecord
    | ImportRecord
    | DiagnosticRecord,
    Field(discriminator="kind"),
]


class AnalysisDetail(ViewModel):
    view: Literal["detail"] = "detail"
    identity: AnalysisIdentity
    focus: Focus
    principal_blockers: Blockers
    page: Page
    records: tuple[Record, ...]


class ReadinessDetail(ViewModel):
    view: Literal["detail"] = "detail"
    identity: ReadinessIdentity
    exit_code: Literal[0, 1]
    focus: Focus
    principal_blockers: Blockers
    page: Page
    records: tuple[Record, ...]


class LocalizedDiagnostic(Diagnostic):
    model_config = ViewModel.model_config
    action: Action | None = None
