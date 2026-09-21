"""Repository readiness v1: static evidence under a supplied policy only."""

from enum import Enum
from typing import Literal, Self

from pydantic import field_validator, model_validator

from apizr.capabilities.model import Digest, Effects
from apizr.capabilities.types import ValueModel
from apizr.execution.policy import EffectName
from apizr.graph.model import Diagnostic as GraphDiagnostic
from apizr.graph.model import ImportDeclaration, Relationship
from apizr.readiness.model import Assessment, State, combine
from apizr.repository.model import Diagnostic as CatalogDiagnostic
from apizr.repository.policy import relative_path

from .execution import ModeCompatibility, execution_compatibility
from .policy import RepositoryReadinessPolicy
from .serialization import policy_digest


class Code(str, Enum):
    INTERFACE = "APIZR-REPOREADY-001"
    GRAPH = "APIZR-REPOREADY-002"
    RELATIONSHIP = "APIZR-REPOREADY-003"
    EFFECT_UNKNOWN = "APIZR-REPOREADY-004"
    EFFECT_TRUE = "APIZR-REPOREADY-005"
    EXECUTION = "APIZR-REPOREADY-006"
    IDENTITY = "APIZR-REPOREADY-007"
    CATALOG = "APIZR-REPOREADY-008"


REASONS: dict[Code, tuple[State, str]] = {
    Code.INTERFACE: (
        State.UNSUPPORTED,
        "Hard interface generation requirement is not met.",
    ),
    Code.GRAPH: (State.CONDITIONAL, "Required graph evidence is unavailable."),
    Code.RELATIONSHIP: (
        State.CONDITIONAL,
        "Required direct relationship evidence is partial.",
    ),
    Code.EFFECT_UNKNOWN: (State.CONDITIONAL, "Required effect evidence is unknown."),
    Code.EFFECT_TRUE: (State.UNSUPPORTED, "A required-false effect is evidenced true."),
    Code.EXECUTION: (
        State.UNSUPPORTED,
        "No declared execution mode supports every required control.",
    ),
    Code.IDENTITY: (
        State.AMBIGUOUS,
        "Relevant catalog/graph identity evidence is ambiguous.",
    ),
    Code.CATALOG: (
        State.CONDITIONAL,
        "Declaration is absent from the trusted Catalog.",
    ),
}


class Reason(ValueModel):
    code: Code
    effect: EffectName | None = None

    @model_validator(mode="after")
    def effect_context(self) -> Self:
        if (self.effect is not None) != (
            self.code in {Code.EFFECT_UNKNOWN, Code.EFFECT_TRUE}
        ):
            raise ValueError("Effect reason must name exactly one effect")
        return self

    @property
    def message(self) -> str:
        return REASONS[self.code][1]


class Dependency(ValueModel):
    capability_id: str
    local_readiness: Assessment
    effects: Effects

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.capability_id != self.local_readiness.capability_id:
            raise ValueError("Dependency identity disagrees with local readiness")
        return self


class Relationships(ValueModel):
    state: Literal["resolved", "partial", "unavailable"]
    diagnostics: tuple[GraphDiagnostic, ...] = ()
    direct: tuple[Relationship, ...] = ()
    module_imports: tuple[Relationship, ...] = ()
    imports: tuple[ImportDeclaration, ...] = ()
    dependencies: tuple[Dependency, ...] = ()


class DeclarationAssessment(ValueModel):
    capability_id: str
    source_path: str
    local_readiness: Assessment
    in_catalog: bool
    effects: Effects
    relationships: Relationships
    reasons: tuple[Reason, ...]
    state: State

    _path = field_validator("source_path")(relative_path)

    @field_validator("reasons")
    @classmethod
    def ordered(cls, values: tuple[Reason, ...]) -> tuple[Reason, ...]:
        return tuple(sorted(set(values), key=lambda r: (r.code.value, r.effect or "")))

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.capability_id != self.local_readiness.capability_id:
            raise ValueError("Declaration identity disagrees with local readiness")
        if self.in_catalog != self.local_readiness.in_ir:
            raise ValueError(
                "Catalog membership must agree with validated IR membership"
            )
        expected = combine(
            (self.local_readiness.state, *(REASONS[r.code][0] for r in self.reasons))
        )
        if self.state != expected:
            raise ValueError(
                "Repository state must derive from local state and repository reasons"
            )
        if (
            self.state == State.READY
            and not self.local_readiness.can_generate_interface
        ):
            raise ValueError("READY requires local interface eligibility")
        return self


class RepositoryReadinessReport(ValueModel):
    schema_version: Literal["apizr.repository-readiness/v1"] = (
        "apizr.repository-readiness/v1"
    )
    repository_digest: Digest
    catalog_digest: Digest
    graph_digest: Digest
    policy: RepositoryReadinessPolicy
    policy_digest: Digest
    execution: tuple[ModeCompatibility, ...]
    catalog_diagnostics: tuple[CatalogDiagnostic, ...]
    graph_diagnostics: tuple[GraphDiagnostic, ...]
    catalog_exit_code: Literal[0, 1]
    graph_complete: bool
    assessments: tuple[DeclarationAssessment, ...]

    @field_validator("assessments")
    @classmethod
    def ordered(
        cls, values: tuple[DeclarationAssessment, ...]
    ) -> tuple[DeclarationAssessment, ...]:
        if len({a.capability_id for a in values}) != len(values):
            raise ValueError("Duplicate repository readiness identities")
        return tuple(sorted(values, key=lambda a: a.capability_id))

    @model_validator(mode="after")
    def bound(self) -> Self:
        if self.policy_digest != policy_digest(self.policy):
            raise ValueError("Repository readiness policy digest mismatch")
        if self.execution != execution_compatibility(self.policy.execution):
            raise ValueError(
                "Execution compatibility disagrees with policy/backend contracts"
            )
        return self

    @property
    def counts(self) -> dict[State, int]:
        return {
            state: sum(a.state == state for a in self.assessments) for state in State
        }

    @property
    def exit_code(self) -> int:
        return int(
            self.catalog_exit_code
            or not self.graph_complete
            or any(a.state != State.READY for a in self.assessments)
        )
