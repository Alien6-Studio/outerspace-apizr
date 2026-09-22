"""Pure fail-closed planning over validated, digest-bound static artifacts."""

from typing import Literal

from apizr.capabilities.types import ValueModel
from apizr.graph.model import CapabilityNode, Graph, ModuleNode
from apizr.graph.serialization import graph_digest
from apizr.readiness.model import Assessment, State
from apizr.repository.model import Catalog
from apizr.repository.serialization import catalog_digest
from apizr.repository_readiness import execution_compatibility, validate_report
from apizr.repository_readiness.model import RepositoryReadinessReport
from apizr.repository_readiness.policy import Mode
from apizr.repository_readiness.serialization import report_digest

from .model import ExposurePlan, ExposureRecord, RelationshipEvidence
from .policy import ExposurePolicy, Interface
from .selector import select_ids
from .serialization import policy_digest


class Diagnostic(ValueModel):
    code: Literal[
        "incomplete_evidence", "unknown_id", "ineligible", "interface", "execution"
    ]
    capability_id: str | None = None
    state: State | None = None
    interface: Interface | None = None


class ExposureRefused(ValueError):
    def __init__(self, diagnostics: tuple[Diagnostic, ...]):
        self.diagnostics = diagnostics
        super().__init__("Requested exposure is refused by evidence/policy")


def interface_compatibility(assessment: Assessment) -> dict[Interface, bool]:
    # These are the shared Interface Contract planner's authoritative eligibility
    # facts. Keep an explicit per-transport adapter so later contract versions can
    # diverge without assuming every transport always has identical eligibility.
    return {
        "rest": assessment.can_generate_interface,
        "mcp": assessment.can_generate_interface,
    }


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
    if readiness.catalog_exit_code or not readiness.graph_complete:
        diagnostics.append(Diagnostic(code="incomplete_evidence"))
    chosen, unknown = select_ids(readiness, policy.selection)
    diagnostics.extend(Diagnostic(code="unknown_id", capability_id=i) for i in unknown)
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
        if assessment.state != State.READY and not (
            assessment.state == State.CONDITIONAL
            and policy.eligibility.allow_conditional
        ):
            diagnostics.append(
                Diagnostic(
                    code="ineligible", capability_id=identity, state=assessment.state
                )
            )
        compatibility = interface_compatibility(assessment.local_readiness)
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
        assert assessment.state == State.READY or assessment.state == State.CONDITIONAL
        relationships = assessment.relationships
        records.append(
            ExposureRecord(
                capability_id=identity,
                module=assessment.local_readiness.source.module,
                source_path=assessment.source_path,
                repository_readiness=assessment.state,
                readiness_reasons=assessment.reasons,
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
