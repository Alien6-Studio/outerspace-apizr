"""Pure fail-closed planning over validated, digest-bound static artifacts."""

from typing import Literal

from pydantic import Field, field_validator

from apizr.capabilities.types import ValueModel
from apizr.graph.model import CapabilityNode, Graph, ModuleNode
from apizr.graph.model import Code as GraphCode
from apizr.graph.serialization import graph_digest
from apizr.readiness.model import Code as LocalCode
from apizr.readiness.model import State
from apizr.repository.model import Catalog
from apizr.repository.model import Code as CatalogCode
from apizr.repository.policy import relative_path
from apizr.repository.serialization import catalog_digest
from apizr.repository_readiness import execution_compatibility, validate_report
from apizr.repository_readiness.eligibility import can_generate_interface
from apizr.repository_readiness.model import (
    DeclarationAssessment,
    RepositoryReadinessReport,
)
from apizr.repository_readiness.policy import Mode
from apizr.repository_readiness.serialization import report_digest

from .model import ExposurePlan, ExposureRecord, RelationshipEvidence
from .policy import ExposurePolicy, Interface
from .scope import EvidenceScope, required_evidence
from .selector import select_ids
from .serialization import policy_digest


class Diagnostic(ValueModel):
    code: Literal[
        "incomplete_evidence", "unknown_id", "ineligible", "interface", "execution"
    ]
    capability_id: str | None = None
    state: State | None = None
    interface: Interface | None = None
    source_path: str | None = None
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=0)
    dependency_path: tuple[str, ...] = ()
    evidence_code: GraphCode | CatalogCode | LocalCode | None = None
    reason: (
        Literal[
            "global", "diagnostic", "initialization", "binding", "execution", "import"
        ]
        | None
    ) = None

    @field_validator("source_path")
    @classmethod
    def relative_source(cls, value: str | None) -> str | None:
        return None if value is None else relative_path(value, allow_root=True)


class ExposureRefused(ValueError):
    def __init__(
        self,
        diagnostics: tuple[Diagnostic, ...],
        *,
        readiness: RepositoryReadinessReport | None = None,
    ):
        self.diagnostics = diagnostics
        self.readiness = readiness
        super().__init__("Requested exposure is refused by evidence/policy")


def interface_compatibility(
    assessment: DeclarationAssessment, *, scope: EvidenceScope | None = None
) -> dict[Interface, bool]:
    # These are the shared Interface Contract planner's authoritative eligibility
    # facts. Keep an explicit per-transport adapter so later contract versions can
    # diverge without assuming every transport always has identical eligibility.
    eligible = (
        can_generate_interface(assessment)
        if scope is None
        else scope.roots[assessment.capability_id].interface_eligible
    )
    return {"rest": eligible, "mcp": eligible}


def plan_exposure(
    catalog: Catalog,
    graph: Graph,
    readiness: RepositoryReadinessReport,
    *,
    policy: ExposurePolicy,
) -> ExposurePlan:
    catalog = Catalog.model_validate(catalog.model_dump(mode="json"))
    graph = Graph.model_validate(graph.model_dump(mode="json"))
    policy = ExposurePolicy.model_validate(policy.model_dump(mode="json"))
    # Also checks every assessment/snapshot, not just digest-shaped fields.
    readiness = validate_report(readiness, catalog, graph)
    diagnostics: list[Diagnostic] = []
    chosen, unknown = select_ids(readiness, policy.selection)
    diagnostics.extend(Diagnostic(code="unknown_id", capability_id=i) for i in unknown)
    scope = required_evidence(catalog, graph, readiness, chosen)
    diagnostics.extend(
        Diagnostic(
            code="incomplete_evidence",
            capability_id=issue.capability_id,
            source_path=issue.source_path,
            line=issue.line,
            column=issue.column,
            dependency_path=issue.dependency_path,
            evidence_code=issue.evidence_code,
            reason=issue.reason,
        )
        for issue in scope.issues
    )
    by_id = {a.capability_id: a for a in readiness.assessments}
    # Readiness's permitted modes remain authoritative. Additional exposure
    # requirements narrow them using the SAME static backend-contract adapter.
    upstream_modes = {m.mode for m in readiness.execution if m.compatible}
    modes: tuple[Mode, ...] = tuple(
        m.mode
        for m in execution_compatibility(policy.execution.requirements())
        if m.compatible and m.mode in upstream_modes
    )
    records: list[ExposureRecord] = []
    for identity in chosen:
        assessment = by_id[identity]
        scoped = scope.roots[identity]
        if scoped.state != State.READY and not (
            scoped.state == State.CONDITIONAL and policy.eligibility.allow_conditional
        ):
            diagnostics.append(
                Diagnostic(
                    code="ineligible", capability_id=identity, state=scoped.state
                )
            )
        compatibility = interface_compatibility(assessment, scope=scope)
        for interface in policy.interfaces:
            if not compatibility[interface]:
                diagnostics.append(
                    Diagnostic(
                        code="interface", capability_id=identity, interface=interface
                    )
                )
        if not modes:
            diagnostics.append(Diagnostic(code="execution", capability_id=identity))
        if any(d.capability_id == identity for d in diagnostics):
            continue
        assert scoped.state == State.READY or scoped.state == State.CONDITIONAL
        relationships = assessment.relationships
        records.append(
            ExposureRecord(
                capability_id=identity,
                module=assessment.local_readiness.source.module,
                source_path=assessment.source_path,
                repository_readiness=scoped.state,
                readiness_reasons=scoped.reasons,
                requested_interfaces=policy.interfaces,
                compatible_interfaces=tuple(
                    i for i in policy.interfaces if compatibility[i]
                ),
                compatible_execution_modes=modes,
                effects=assessment.effects,
                relationships=RelationshipEvidence(
                    state=relationships.state,
                    diagnostics=relationships.diagnostics,
                    direct=relationships.direct,
                    module_imports=relationships.module_imports,
                    imports=relationships.imports,
                ),
            )
        )
    if diagnostics:
        raise ExposureRefused(tuple(diagnostics))
    targets = {
        r.target
        for record in records
        for r in (*record.relationships.direct, *record.relationships.module_imports)
    }
    support = {record.module for record in records}
    external: set[str] = set()
    for node in graph.nodes:
        if node.id in targets:
            if isinstance(node, (ModuleNode, CapabilityNode)):
                support.add(node.module)
            else:
                external.add(node.module)
    return ExposurePlan(
        repository_digest=catalog.repository_digest,
        catalog_digest=catalog_digest(catalog),
        graph_digest=graph_digest(graph),
        repository_readiness_digest=report_digest(readiness),
        exposure_policy_digest=policy_digest(policy),
        interfaces=policy.interfaces,
        capabilities=tuple(records),
        observed_support_modules=tuple(support),
        external_modules=tuple(external),
    )


def validate_plan(
    plan: ExposurePlan,
    catalog: Catalog,
    graph: Graph,
    readiness: RepositoryReadinessReport,
    *,
    policy: ExposurePolicy,
) -> ExposurePlan:
    validated = ExposurePlan.model_validate(plan.model_dump(mode="json"))
    if validated != plan_exposure(catalog, graph, readiness, policy=policy):
        raise ValueError("Exposure plan disagrees with bound evidence/policy")
    return validated
