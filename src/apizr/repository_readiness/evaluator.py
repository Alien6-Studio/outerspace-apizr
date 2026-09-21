"""Pure deterministic assessment of two already-reviewed, linked artifacts."""

from apizr.capabilities.model import Effects, EffectValue
from apizr.execution.policy import EffectName
from apizr.graph.model import Code as GraphCode
from apizr.graph.model import Graph
from apizr.graph.serialization import graph_digest
from apizr.readiness.model import combine
from apizr.repository.model import Catalog
from apizr.repository.serialization import catalog_digest

from .evidence import relationship_evidence, validate_linkage
from .execution import execution_compatibility
from .model import (
    REASONS,
    Code,
    DeclarationAssessment,
    Reason,
    RepositoryReadinessReport,
)
from .policy import RepositoryReadinessPolicy
from .serialization import policy_digest


def assess_repository(
    catalog: Catalog,
    graph: Graph,
    *,
    policy: RepositoryReadinessPolicy | None = None,
) -> RepositoryReadinessReport:
    # Roundtrip rejects unchecked model_copy/model_construct at every nested level.
    catalog = Catalog.model_validate(catalog.model_dump(mode="json"))
    graph = Graph.model_validate(graph.model_dump(mode="json"))
    selected = (
        RepositoryReadinessPolicy()
        if policy is None
        else RepositoryReadinessPolicy.model_validate(policy.model_dump(mode="json"))
    )
    validate_linkage(catalog, graph)
    local = {
        a.capability_id: a
        for s in catalog.sources
        if s.inspection
        for a in s.inspection.readiness.assessments
    }
    effects = {
        c.id: c.effects
        for s in catalog.sources
        if s.inspection
        for c in s.inspection.capability_ir.capabilities
    }
    execution = execution_compatibility(selected.execution)
    assessments: list[DeclarationAssessment] = []
    for source in catalog.sources:
        if source.inspection is None:
            continue
        for upstream in source.inspection.readiness.assessments:
            identity = upstream.capability_id
            in_catalog = identity in effects
            observed = effects.get(identity, Effects())
            relationships = relationship_evidence(
                upstream, source.path, in_catalog, graph, local, effects
            )
            reasons: list[Reason] = []
            if selected.require_interface and not upstream.can_generate_interface:
                reasons.append(Reason(code=Code.INTERFACE))
            if not in_catalog:
                reasons.append(Reason(code=Code.CATALOG))
            if any(
                d.code in {GraphCode.COLLISION, GraphCode.IMPORT}
                for d in relationships.diagnostics
            ) or any(
                n.resolution == "ambiguous"
                for d in relationships.imports
                for n in d.names
            ):
                reasons.append(Reason(code=Code.IDENTITY))
            if (
                selected.relationships.require_resolved
                and relationships.state != "resolved"
            ):
                reasons.append(
                    Reason(
                        code=Code.GRAPH
                        if relationships.state == "unavailable"
                        else Code.RELATIONSHIP
                    )
                )
            required: set[EffectName] = set(selected.effects.require_known) | set(
                selected.effects.require_false
            )
            for name in sorted(required):
                effect = getattr(observed, name)
                if effect.value == EffectValue.UNKNOWN:
                    reasons.append(Reason(code=Code.EFFECT_UNKNOWN, effect=name))
                elif (
                    name in selected.effects.require_false
                    and effect.value == EffectValue.TRUE
                ):
                    reasons.append(Reason(code=Code.EFFECT_TRUE, effect=name))
            if not any(mode.compatible for mode in execution):
                reasons.append(Reason(code=Code.EXECUTION))
            assessments.append(
                DeclarationAssessment(
                    capability_id=identity,
                    source_path=source.path,
                    local_readiness=upstream,
                    in_catalog=in_catalog,
                    effects=observed,
                    relationships=relationships,
                    reasons=tuple(reasons),
                    state=combine(
                        (upstream.state, *(REASONS[r.code][0] for r in reasons))
                    ),
                )
            )
    return RepositoryReadinessReport(
        repository_digest=catalog.repository_digest,
        catalog_digest=catalog_digest(catalog),
        graph_digest=graph_digest(graph),
        policy=selected,
        policy_digest=policy_digest(selected),
        execution=execution,
        catalog_diagnostics=catalog.diagnostics,
        graph_diagnostics=graph.diagnostics,
        catalog_exit_code=graph.catalog_exit_code,
        graph_complete=graph.complete,
        assessments=tuple(assessments),
    )


def validate_report(
    report: RepositoryReadinessReport,
    catalog: Catalog,
    graph: Graph,
) -> RepositoryReadinessReport:
    """Verify all conclusions and evidence against the original bound artifacts."""
    validated = RepositoryReadinessReport.model_validate(report.model_dump(mode="json"))
    expected = assess_repository(catalog, graph, policy=validated.policy)
    if validated != expected:
        raise ValueError("Repository readiness report disagrees with bound artifacts")
    return validated
