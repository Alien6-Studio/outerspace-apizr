"""Selected execution proof over the full immutable, digest-bound audit.

Validate the complete inputs before composing dependency admission, lexical
initialization and per-root readiness. No source or runtime is consulted.
"""

from types import MappingProxyType

from apizr.graph.model import CapabilityNode, Graph, ModuleNode
from apizr.readiness.model import Code as LocalCode
from apizr.readiness.model import State, combine
from apizr.repository.model import Catalog
from apizr.repository_readiness import validate_report
from apizr.repository_readiness.eligibility import interface_state, proven_import
from apizr.repository_readiness.model import REASONS, RepositoryReadinessReport
from apizr.repository_readiness.model import Code as RepositoryCode

from .scope_admission import node_issues
from .scope_index import EvidenceIndex
from .scope_initialization import initialization_cycles
from .scope_model import EvidenceScope, ScopedRoot


def _scope_root(index: EvidenceIndex, identity: str) -> ScopedRoot:
    paths = index.paths(identity)
    issues = [
        issue
        for node, path in paths.items()
        for issue in node_issues(index, identity, node, path)
    ]
    issues.extend(initialization_cycles(index, identity, paths))
    execution_ready = frozenset(
        node for node in paths if isinstance(index.nodes.get(node), CapabilityNode)
    )
    initialized_modules = frozenset(
        node for node in paths if isinstance(index.nodes.get(node), ModuleNode)
    )
    # All required nodes are checked before optimistic mutual dependency
    # support is used. No invalid root can produce a successful plan.
    refined: dict[str, State] = {}
    for node in sorted(execution_ready):
        assessment = index.assessments[node]
        state = interface_state(
            assessment.local_readiness,
            assessment.source_path,
            assessment.relationships,
            execution_ready=execution_ready,
            initialized_modules=initialized_modules,
            scope_complete=not issues,
            external_modules=index.external_modules,
        )
        refined[node] = state
        local = assessment.local_readiness
        if local.dimensions.execution.state != State.READY and any(
            reason.code == LocalCode.DEPENDENCY
            for reason in local.dimensions.execution.reasons
        ):
            # Interface state also includes private input/output facts;
            # test only execution using the shared exact-import predicate.
            for reason in local.dimensions.execution.reasons:
                if reason.code != LocalCode.DEPENDENCY:
                    continue
                declarations = [
                    d for d in assessment.relationships.imports if d.line == reason.line
                ]
                if not declarations or not all(
                    proven_import(
                        d,
                        assessment.relationships,
                        execution_ready=execution_ready,
                        initialized_modules=initialized_modules,
                        external_modules=index.external_modules,
                    )
                    for d in declarations
                ):
                    issues.append(
                        index.issue(
                            identity,
                            paths[node],
                            assessment.source_path,
                            reason.code,
                            "import",
                            reason.line,
                        )
                    )
    assessment = index.assessments[identity]
    state = refined.get(identity, assessment.state)
    # Wheel membership resolves provider identity only. External code is
    # still opaque and needs explicit conditional exposure; no READY claim.
    conditional_provider = bool(index.external_modules) and any(
        reason.code == LocalCode.DEPENDENCY
        and any(
            declaration.line == reason.line
            and any(name.resolution == "external" for name in declaration.names)
            for declaration in index.assessments[node].relationships.imports
        )
        for node in execution_ready
        for reason in index.assessments[
            node
        ].local_readiness.dimensions.execution.reasons
    )
    reasons = tuple(
        reason
        for reason in assessment.reasons
        if not (
            reason.code in {RepositoryCode.INTERFACE, RepositoryCode.RELATIONSHIP}
            and state == State.READY
            and not issues
        )
    )
    state = combine((state, *(REASONS[reason.code][0] for reason in reasons)))
    if conditional_provider:
        state = combine((state, State.CONDITIONAL))
    issues = sorted(
        set(issues),
        key=lambda issue: (
            len(issue.dependency_path),
            issue.dependency_path,
            issue.source_path or "",
            issue.line or 0,
            issue.column or 0,
            issue.evidence_code.value,
            issue.reason,
        ),
    )
    return ScopedRoot(
        state,
        refined.get(identity) == State.READY,
        reasons,
        tuple(sorted(paths)),
        tuple(issues),
    )


def required_evidence(
    catalog: Catalog,
    graph: Graph,
    readiness: RepositoryReadinessReport,
    roots: tuple[str, ...],
) -> EvidenceScope:
    """Authoritative scope; callers cannot supply paths or proof overrides.

    Roundtrip rejects unchecked nested models and recomputes report linkage.
    The full artifacts remain untouched and remain the successful plan's identity.
    """
    catalog = Catalog.model_validate(catalog.model_dump(mode="json"))
    graph = Graph.model_validate(graph.model_dump(mode="json"))
    readiness = validate_report(readiness, catalog, graph)
    index = EvidenceIndex(catalog, graph, readiness)
    if any(root not in index.assessments for root in roots):
        raise ValueError("Scope roots must be known readiness identities")
    scoped = {root: _scope_root(index, root) for root in sorted(set(roots))}
    global_issues = tuple(
        sorted(
            set(index.global_issues),
            key=lambda issue: (
                issue.source_path or "",
                issue.line or 0,
                issue.column or 0,
                issue.evidence_code.value,
            ),
        )
    )
    return EvidenceScope(MappingProxyType(scoped), global_issues)
