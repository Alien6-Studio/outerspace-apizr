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
REPOSITORY_PIN_DESCRIPTION = (
    "Optional consistency pin: omit or use null to discover normally without asserting "
    "a previous identity, or supply a lowercase 64-character hexadecimal SHA-256 value. "
    "Copy repository_digest.value from a previous full result, or "
    "identity.repository_digest.value from a bounded view. This plain value is the "
    "repository evidence identity expected from this call's discovery of the startup "
    "source scope; it does not select another repository. A mismatch is refused with "
    "repository_changed. Digest objects, algorithm prefixes and uppercase are invalid."
)
READINESS_EXIT_DESCRIPTION = (
    "Business readiness outcome: 0 denotes a successful readiness result under the "
    "assessment policy; 1 can be a valid assessment with isError: false. It is not an "
    "MCP transport or runtime failure. Consult the retained states and reasons: "
    "CONDITIONAL is not READY, and unknown or ambiguous evidence is not proof of failure."
)
# Valid illustrative schema value; runtime clients must use their observed identity.
PIN_EXAMPLE = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
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
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {},
                {"view": "summary"},
                {"expected_repository_digest": PIN_EXAMPLE},
                {
                    "view": "detail",
                    "capability_id": "python:model:predict",
                    "limit": 50,
                },
            ]
        }
    )

    view: Literal["full", "summary", "detail"] = Field(
        default="full",
        description=(
            "full returns the complete canonical artifact/report; summary returns bounded "
            "evidence for compact inspection; detail focuses on exactly one capability or "
            "module and can paginate ancillary records. Reduced views are not partial "
            "canonical Catalog, Graph or Readiness artifacts."
        ),
    )
    capability_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=1024,
        description=(
            "Exact canonical capability ID, for example python:model:predict. Only for "
            "detail, with module omitted/null. No fuzzy matching, source-path matching or "
            "implicit capability selection."
        ),
    )
    module: str | None = Field(
        default=None,
        min_length=1,
        max_length=512,
        description=(
            "One exact logical module name, for example package.model, not a source path. "
            "Only for detail, with capability_id omitted/null."
        ),
    )
    offset: int | None = Field(
        default=None,
        ge=0,
        le=2147483647,
        description=(
            "Zero-based offset into deterministically ordered ancillary detail records "
            "after filtering; defaults to 0. Only detail accepts pagination. A nonzero "
            "offset requires expected_repository_digest. Use page.next_offset with the "
            "same filter; there is no persistent server-side pagination session."
        ),
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=MAX_LIMIT,
        description=(
            "Maximum ancillary records in a detail page, from 1 to 200; omitted/null "
            "uses 50. Focus and principal blockers are not paged away. The response byte "
            "bound still applies and may refuse even one large record."
        ),
    )
    expected_repository_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$", description=REPOSITORY_PIN_DESCRIPTION
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
    repository_digest: Digest = Field(
        description="Complete repository evidence identity; copy value to expected_repository_digest for consistency pinning."
    )
    catalog_digest: Digest = Field(
        description="Digest of the complete canonical static Catalog, unchanged by filtering or pagination."
    )
    graph_digest: Digest = Field(
        description="Digest of the complete canonical static Graph, unchanged by filtering or pagination."
    )


class ReadinessIdentity(AnalysisIdentity):
    repository_readiness_digest: Digest = Field(
        description="Digest of the complete canonical repository readiness report, not just the displayed view."
    )
    readiness_policy_digest: Digest = Field(
        description="Digest of the readiness assessment policy used for this evidence."
    )


class Page(ViewModel):
    offset: int = Field(
        ge=0,
        description="Zero-based offset in the complete filtered and deterministically ordered record collection.",
    )
    limit: int = Field(
        ge=1,
        le=MAX_LIMIT,
        description="Maximum records requested for this page; not a response byte limit.",
    )
    total: int = Field(
        ge=0,
        description="Total records in the complete filtered collection before pagination.",
    )
    returned: int = Field(
        ge=0, description="Number of records actually included in this page."
    )
    next_offset: int | None = Field(
        default=None,
        ge=1,
        description="Offset for the next page, or null when complete; continue with the same filter and repository digest pin.",
    )
    complete: bool = Field(
        description="True when no subsequent page remains; does not assert that static evidence itself is complete."
    )

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
    view: Literal["summary"] = Field(
        default="summary",
        description="Bounded summary variant, not a partial canonical Catalog or Graph.",
    )
    identity: AnalysisIdentity = Field(
        description="Identities of the complete static artifacts underlying this bounded view."
    )
    summary: AnalysisCounts = Field(
        description="Static source, capability, relationship and diagnostic counts; no project execution is implied."
    )
    principal_blockers: Blockers = Field(
        description="Bounded sample of at most ten principal diagnostics with total and has_more; not all evidence."
    )


class ReadinessSummary(ViewModel):
    view: Literal["summary"] = Field(
        default="summary",
        description="Bounded readiness summary, not a partial canonical readiness report.",
    )
    identity: ReadinessIdentity = Field(
        description="Complete repository, artifact and readiness-policy identities underlying this view."
    )
    exit_code: Literal[0, 1] = Field(description=READINESS_EXIT_DESCRIPTION)
    states: dict[State, int] = Field(
        description="Counts by canonical readiness state; conditional and ambiguous evidence remain distinct from ready evidence."
    )
    execution: tuple[ModeCompatibility, ...] = Field(
        description="Static execution-mode compatibility under the readiness policy, not execution authority or proof of successful execution."
    )
    principal_blockers: Blockers = Field(
        description="Bounded sample of at most ten principal diagnostics with total and has_more; not all evidence."
    )


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
    view: Literal["detail"] = Field(
        default="detail",
        description="Focused static evidence view, not a partial canonical Catalog or Graph.",
    )
    identity: AnalysisIdentity = Field(
        description="Identities of the complete static artifacts; filtering and paging do not change them."
    )
    focus: Focus = Field(
        description="The exactly selected capability or logical module with its static evidence and readiness states; never paged away."
    )
    principal_blockers: Blockers = Field(
        description="Bounded principal diagnostic sample for this focus with complete count and has_more."
    )
    page: Page = Field(
        description="Pagination metadata for ancillary records after deterministic filtering and ordering."
    )
    records: tuple[Record, ...] = Field(
        description="Current page of ancillary static source, dependency, relationship, import or diagnostic evidence; dependencies are not implicitly exposed."
    )


class ReadinessDetail(ViewModel):
    view: Literal["detail"] = Field(
        default="detail",
        description="Focused readiness view, not a partial canonical readiness report.",
    )
    identity: ReadinessIdentity = Field(
        description="Complete repository, artifact and readiness-policy identities underlying this view."
    )
    exit_code: Literal[0, 1] = Field(description=READINESS_EXIT_DESCRIPTION)
    focus: Focus = Field(
        description="Exactly selected capability or module; local, repository and selected readiness evidence remain distinct and are never paged away."
    )
    principal_blockers: Blockers = Field(
        description="Bounded principal diagnostic sample for this focus with complete count and has_more."
    )
    page: Page = Field(
        description="Pagination metadata for ancillary records after deterministic filtering and ordering."
    )
    records: tuple[Record, ...] = Field(
        description="Current page of ancillary evidence supporting readiness; unknown evidence is retained and does not imply successful project execution."
    )


class LocalizedDiagnostic(Diagnostic):
    model_config = ViewModel.model_config
    action: Action | None = None
