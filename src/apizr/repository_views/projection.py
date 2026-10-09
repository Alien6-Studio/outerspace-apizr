"""Filter canonical evidence, order the entire slice, then page ancillary records.

No discovery, source access, execution or MCP transport. Digest functions retain
their existing canonical validation; required_evidence owns dependency traversal.
"""

from collections.abc import Iterable
from itertools import chain
from typing import Literal

from apizr.capabilities.model import Severity
from apizr.exposure.planner import Diagnostic
from apizr.exposure.scope import ScopeIssue, required_evidence
from apizr.graph.model import Graph, ModuleNode, RelationshipKind, module_id
from apizr.graph.serialization import graph_digest
from apizr.readiness.model import POLICY, State
from apizr.repository.model import Catalog, SourceUnit
from apizr.repository_readiness.model import RepositoryReadinessReport
from apizr.repository_readiness.serialization import report_digest

from .model import (
    DEFAULT_LIMIT,
    MAX_BLOCKERS,
    Action,
    AnalysisCounts,
    AnalysisDetail,
    AnalysisIdentity,
    AnalysisSummary,
    Blockers,
    CapabilityFocus,
    CapabilityRecord,
    DependencyRecord,
    DiagnosticRecord,
    EvidenceDiagnostic,
    Focus,
    ImportRecord,
    LocalizedDiagnostic,
    ModuleFocus,
    Page,
    ReadinessDetail,
    ReadinessIdentity,
    ReadinessSummary,
    Record,
    RelationshipRecord,
    SourceRecord,
    SourceView,
    ViewQuery,
)


class ViewRefused(ValueError):
    def __init__(self, code: Literal["unknown_capability", "unknown_module"]):
        self.code = code
        super().__init__(code)


def action(code: str, reason: str | None = None) -> Action | None:
    if code == "unknown_id":
        return "select_known_capability"
    if (
        code
        in {
            "APIZR-GRAPH-002",
            "APIZR-GRAPH-003",
            "APIZR-GRAPH-004",
            "APIZR-GRAPH-005",
            "APIZR-READY-014",
            "APIZR-READY-015",
        }
        or reason == "import"
    ):
        return "fix_import"
    if reason == "binding" or code in {
        "APIZR-GRAPH-006",
        "APIZR-READY-001",
        "APIZR-READY-003",
        "APIZR-READY-008",
        "APIZR-READY-009",
        "APIZR-READY-010",
    }:
        return "fix_binding"
    if reason == "initialization" or code == "APIZR-READY-004":
        return "fix_initialization"
    if code in {
        "interface",
        "ineligible",
        "APIZR-REPOREADY-001",
        "APIZR-READY-011",
        "APIZR-READY-012",
        "APIZR-READY-013",
        "APIZR-READY-017",
        "APIZR-READY-019",
    }:
        return "resolve_interface_contract"
    if reason == "execution" or code in {"execution", "APIZR-REPOREADY-006"}:
        return "adjust_execution_requirements"
    return "inspect_dependency" if reason in {"diagnostic", "global"} else None


def localize(diagnostic: Diagnostic) -> LocalizedDiagnostic:
    return LocalizedDiagnostic(
        **diagnostic.model_dump(),
        action=action(
            diagnostic.evidence_code.value
            if diagnostic.evidence_code is not None
            else diagnostic.code,
            diagnostic.reason,
        ),
    )


def scoped(issue: ScopeIssue) -> EvidenceDiagnostic:
    return EvidenceDiagnostic(
        origin="scope",
        code=issue.evidence_code.value,
        capability_id=issue.capability_id,
        source_path=issue.source_path,
        line=issue.line,
        column=issue.column,
        dependency_path=issue.dependency_path,
        reason=issue.reason,
        action=action(issue.evidence_code.value, issue.reason),
    )


def blockers(items: Iterable[EvidenceDiagnostic]) -> Blockers:
    count = 0
    shown: list[EvidenceDiagnostic] = []
    for item in items:
        count += 1
        if len(shown) < MAX_BLOCKERS:
            shown.append(item)
    return Blockers(total=count, shown=tuple(shown), has_more=count > len(shown))


def audit_diagnostics(
    catalog: Catalog,
    graph: Graph,
    paths: set[str] | None = None,
    *,
    blocking: bool = True,
) -> Iterable[EvidenceDiagnostic]:
    for diagnostic in catalog.diagnostics:
        if (not blocking or diagnostic.severity == Severity.ERROR) and (
            paths is None or diagnostic.path in paths
        ):
            yield EvidenceDiagnostic(
                origin="catalog",
                code=diagnostic.code.value,
                source_path=diagnostic.path,
                line=diagnostic.line,
            )
    for diagnostic in graph.diagnostics:
        if (not blocking or diagnostic.severity == Severity.ERROR) and (
            paths is None or diagnostic.path in paths
        ):
            yield EvidenceDiagnostic(
                origin="graph",
                code=diagnostic.code.value,
                source_path=diagnostic.path,
                line=diagnostic.line,
                column=diagnostic.column,
                action=action(diagnostic.code.value),
            )


def readiness_diagnostics(
    report: RepositoryReadinessReport,
    paths: set[str] | None = None,
) -> Iterable[EvidenceDiagnostic]:
    for assessment in report.assessments:
        if assessment.state == State.READY or (
            paths is not None and assessment.source_path not in paths
        ):
            continue
        local = assessment.local_readiness
        for dimension in (
            local.dimensions.binding,
            local.dimensions.execution,
            local.dimensions.inputs,
            local.dimensions.outputs,
        ):
            for reason in dimension.reasons:
                if POLICY[reason.code][0] != State.READY:
                    yield EvidenceDiagnostic(
                        origin="readiness",
                        code=reason.code.value,
                        capability_id=assessment.capability_id,
                        source_path=assessment.source_path,
                        line=reason.line,
                        action=action(reason.code.value),
                    )
        for reason in assessment.reasons:
            yield EvidenceDiagnostic(
                origin="readiness",
                code=reason.code.value,
                capability_id=assessment.capability_id,
                source_path=assessment.source_path,
                line=local.source.line,
                action=action(reason.code.value),
            )


def source_view(unit: SourceUnit) -> SourceView:
    return SourceView(
        path=unit.path,
        module=unit.module,
        source_digest=unit.source_digest,
        size=unit.size,
        inspected=unit.inspection is not None,
        is_package=unit.is_package,
    )


def page_records(
    records: Iterable[Record], query: ViewQuery
) -> tuple[Page, tuple[Record, ...]]:
    # Canonical JSON uses the already typed, filtered records only. No full
    # Catalog/Graph/Readiness dump or dependence on insertion/hash order.
    ordered = tuple(sorted(records, key=lambda r: r.model_dump_json()))
    offset, limit = query.offset or 0, query.limit or DEFAULT_LIMIT
    selected = ordered[offset : offset + limit]
    more = offset + len(selected) < len(ordered)
    return (
        Page(
            offset=offset,
            limit=limit,
            total=len(ordered),
            returned=len(selected),
            next_offset=offset + len(selected) if more else None,
            complete=not more,
        ),
        selected,
    )


def detail(
    catalog: Catalog,
    graph: Graph,
    report: RepositoryReadinessReport,
    query: ViewQuery,
) -> tuple[Focus, Blockers, Page, tuple[Record, ...]]:
    assessments = {a.capability_id: a for a in report.assessments}
    entries = {c.id: c for c in catalog.capabilities}
    nodes = {n.id: n for n in graph.nodes}
    records: list[Record] = []
    if query.capability_id is not None:
        identity = query.capability_id
        assessment = assessments.get(identity)
        if assessment is None:
            raise ViewRefused("unknown_capability")
        scope = required_evidence(catalog, graph, report, (identity,))
        root = scope.roots[identity]
        focus: Focus = CapabilityFocus(
            capability_id=identity,
            module=assessment.local_readiness.source.module,
            source_path=assessment.source_path,
            capability=entries.get(identity),
            local_readiness=assessment.local_readiness,
            repository_state=assessment.state,
            selected_state=root.state,
            interface_eligible=root.interface_eligible and not scope.global_issues,
            global_evidence_complete=not scope.global_issues,
            reasons=root.reasons,
        )
        ids = set(root.required_ids)
        for required in root.required_ids:
            if required != identity:
                records.append(DependencyRecord(id=required, node=nodes.get(required)))
        diagnostics = tuple(scoped(issue) for issue in scope.issues)
        primary = diagnostics
        if root.state != State.READY:
            primary += tuple(
                EvidenceDiagnostic(
                    origin="readiness",
                    code=reason.code.value,
                    capability_id=identity,
                    source_path=assessment.source_path,
                    line=assessment.local_readiness.source.line,
                    action=action(reason.code.value),
                )
                for reason in root.reasons
            )
        relevant_paths = {
            n.path
            for identity in ids
            if isinstance((n := nodes.get(identity)), ModuleNode)
        }
    else:
        module = query.module
        units = tuple(u for u in catalog.sources if u.module == module)
        if not units or module is None:
            raise ViewRefused("unknown_module")
        module_assessments = tuple(
            a for a in report.assessments if a.local_readiness.source.module == module
        )
        node = nodes.get(module_id(module))
        focus = ModuleFocus(
            module=module,
            source_count=len(units),
            source=source_view(units[0]) if len(units) == 1 else None,
            node=node if isinstance(node, ModuleNode) else None,
            capability_count=len(module_assessments),
            states={
                state: sum(a.state == state for a in module_assessments)
                for state in State
            },
        )
        ids = {module_id(module), *(a.capability_id for a in module_assessments)}
        relevant_paths = {u.path for u in units}
        for assessment in module_assessments:
            records.append(
                CapabilityRecord(
                    capability_id=assessment.capability_id,
                    source_path=assessment.source_path,
                    capability=entries.get(assessment.capability_id),
                    local_state=assessment.local_readiness.state,
                    state=assessment.state,
                )
            )
        diagnostics = tuple(
            chain(
                audit_diagnostics(catalog, graph, relevant_paths),
                readiness_diagnostics(report, relevant_paths),
            )
        )
        primary = diagnostics
        diagnostics = tuple(
            chain(
                audit_diagnostics(catalog, graph, relevant_paths, blocking=False),
                readiness_diagnostics(report, relevant_paths),
            )
        )
    for unit in catalog.sources:
        if unit.path in relevant_paths:
            records.append(SourceRecord(source=source_view(unit)))
    for edge in graph.relationships:
        if edge.source in ids and (
            edge.kind != RelationshipKind.CONTAINS or edge.target in ids
        ):
            records.append(RelationshipRecord(relationship=edge))
    for declaration in graph.imports:
        if declaration.source in ids:
            records.append(ImportRecord(declaration=declaration))
    records.extend(DiagnosticRecord(diagnostic=d) for d in diagnostics)
    page, selected = page_records(records, query)
    return focus, blockers(primary), page, selected


def analyze_view(
    catalog: Catalog,
    graph: Graph,
    query: ViewQuery,
    report: RepositoryReadinessReport | None = None,
) -> AnalysisSummary | AnalysisDetail:
    identity = AnalysisIdentity(
        repository_digest=catalog.repository_digest,
        catalog_digest=graph.catalog_digest,
        graph_digest=graph_digest(graph),
    )
    if query.view == "summary":
        return AnalysisSummary(
            identity=identity,
            summary=AnalysisCounts(
                sources=len(catalog.sources),
                inspected_sources=sum(
                    u.inspection is not None for u in catalog.sources
                ),
                capabilities=len(catalog.capabilities),
                modules=sum(n.kind == "module" for n in graph.nodes),
                relationships=len(graph.relationships),
                imports=len(graph.imports),
                graph_complete=graph.complete,
                catalog_diagnostics=len(catalog.diagnostics),
                graph_diagnostics=len(graph.diagnostics),
            ),
            principal_blockers=blockers(audit_diagnostics(catalog, graph)),
        )
    if query.view != "detail" or report is None:
        raise ValueError("Detail requires assessed canonical evidence")
    focus, principal, page, records = detail(catalog, graph, report, query)
    return AnalysisDetail(
        identity=identity,
        focus=focus,
        principal_blockers=principal,
        page=page,
        records=records,
    )


def readiness_view(
    catalog: Catalog,
    graph: Graph,
    report: RepositoryReadinessReport,
    query: ViewQuery,
) -> ReadinessSummary | ReadinessDetail:
    identity = ReadinessIdentity(
        repository_digest=report.repository_digest,
        catalog_digest=report.catalog_digest,
        graph_digest=report.graph_digest,
        repository_readiness_digest=report_digest(report),
        readiness_policy_digest=report.policy_digest,
    )
    if query.view == "summary":
        return ReadinessSummary(
            identity=identity,
            exit_code=1 if report.exit_code else 0,
            states=report.counts,
            execution=report.execution,
            principal_blockers=blockers(
                chain(audit_diagnostics(catalog, graph), readiness_diagnostics(report))
            ),
        )
    if query.view != "detail":
        raise ValueError("Reduced readiness requires an explicit view")
    focus, principal, page, records = detail(catalog, graph, report, query)
    return ReadinessDetail(
        identity=identity,
        exit_code=1 if report.exit_code else 0,
        focus=focus,
        principal_blockers=principal,
        page=page,
        records=records,
    )
