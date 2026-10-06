"""Selected execution proof over the full immutable, digest-bound audit.

Calls, callable references and local imports require execution support, never
public selection. Containment is not a dependency. Module imports and package
ancestors require initialization. No source, resolver or runtime is consulted.
"""

from collections import defaultdict, deque
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from apizr.capabilities.model import Severity
from apizr.graph.model import (
    CapabilityNode,
    Graph,
    ImportDeclaration,
    ModuleNode,
    Relationship,
    RelationshipKind,
    module_id,
)
from apizr.graph.model import (
    Code as GraphCode,
)
from apizr.graph.model import (
    Diagnostic as GraphDiagnostic,
)
from apizr.readiness.model import Code as LocalCode
from apizr.readiness.model import State, combine
from apizr.repository.model import Catalog
from apizr.repository.model import Code as CatalogCode
from apizr.repository_readiness import validate_report
from apizr.repository_readiness.eligibility import interface_state, proven_import
from apizr.repository_readiness.initialization import initialization_reasons
from apizr.repository_readiness.model import (
    REASONS,
    DeclarationAssessment,
    Reason,
    RepositoryReadinessReport,
)
from apizr.repository_readiness.model import (
    Code as RepositoryCode,
)


@dataclass(frozen=True)
class ScopeIssue:
    capability_id: str | None
    dependency_path: tuple[str, ...]
    source_path: str | None
    line: int | None
    column: int | None
    evidence_code: GraphCode | CatalogCode | LocalCode
    reason: Literal[
        "global", "diagnostic", "initialization", "binding", "execution", "import"
    ]


@dataclass(frozen=True)
class ScopedRoot:
    state: State
    interface_eligible: bool
    reasons: tuple[Reason, ...]
    required_ids: tuple[str, ...]
    issues: tuple[ScopeIssue, ...]


@dataclass(frozen=True)
class EvidenceScope:
    roots: Mapping[str, ScopedRoot]
    global_issues: tuple[ScopeIssue, ...]

    @property
    def issues(self) -> tuple[ScopeIssue, ...]:
        return self.global_issues + tuple(
            issue for root in self.roots.values() for issue in root.issues
        )


_FOLLOW = {
    RelationshipKind.CALL,
    RelationshipKind.REFERENCE,
    RelationshipKind.CAPABILITY,
    RelationshipKind.MODULE,
}
_GLOBAL_GRAPH = {GraphCode.INPUT, GraphCode.LIMIT, GraphCode.COLLISION}
_LOCAL_CATALOG = {
    CatalogCode.PARSE,
    CatalogCode.ENCODING,
    CatalogCode.ANALYSIS,
    CatalogCode.SIZE,
    CatalogCode.READ,
}


class _Index:
    def __init__(
        self, catalog: Catalog, graph: Graph, report: RepositoryReadinessReport
    ):
        self.nodes = {node.id: node for node in graph.nodes}
        self.units = {unit.path: unit for unit in catalog.sources}
        self.modules = {
            unit.module: unit for unit in catalog.sources if unit.module is not None
        }
        self.assessments = {item.capability_id: item for item in report.assessments}
        self.edges: dict[str, list[Relationship]] = defaultdict(list)
        self.imports: dict[str, list[ImportDeclaration]] = defaultdict(list)
        self.diagnostics: dict[str, list[GraphDiagnostic]] = defaultdict(list)
        self.catalog_errors: dict[str, list[CatalogCode]] = defaultdict(list)
        self.spans: dict[str, list[DeclarationAssessment]] = defaultdict(list)
        self.global_issues: list[ScopeIssue] = []
        # Full inspected-source copying is unchanged. A contradictory import
        # tree invalidates that entire manifest in the reviewed loader, even
        # if the selected root does not import the colliding namespace.
        for unit in catalog.sources:
            if unit.inspection is None or unit.module is None:
                continue
            parts = unit.module.split(".")
            for length in range(1, len(parts)):
                parent = self.modules.get(".".join(parts[:length]))
                if (
                    parent is not None
                    and parent.inspection is not None
                    and not parent.is_package
                ):
                    self.global_issues.append(
                        self.issue(None, (), unit.path, GraphCode.COLLISION, "global")
                    )
        for assessment in report.assessments:
            self.spans[assessment.source_path].append(assessment)
        for edge in graph.relationships:
            self.edges[edge.source].append(edge)
        for declaration in graph.imports:
            self.imports[declaration.source].append(declaration)
        for diagnostic in graph.diagnostics:
            if (
                diagnostic.code in _GLOBAL_GRAPH
                or diagnostic.path not in self.units
                or self.units[diagnostic.path].module is None
            ):
                self.global_issues.append(
                    self.issue(
                        None,
                        (),
                        diagnostic.path,
                        diagnostic.code,
                        "global",
                        diagnostic.line,
                        diagnostic.column,
                    )
                )
            else:
                self.diagnostics[self.owner(diagnostic)].append(diagnostic)
        for diagnostic in catalog.diagnostics:
            if diagnostic.severity != Severity.ERROR:
                continue
            unit = self.units.get(diagnostic.path)
            if (
                diagnostic.code in _LOCAL_CATALOG
                and unit is not None
                and unit.module is not None
            ):
                self.catalog_errors[module_id(unit.module)].append(diagnostic.code)
            else:
                self.global_issues.append(
                    self.issue(
                        None,
                        (),
                        diagnostic.path,
                        diagnostic.code,
                        "global",
                        diagnostic.line,
                    )
                )
        # Incomplete bits without explaining location-bound evidence do not
        # establish independence. They are never interpreted as a clean audit.
        explained_catalog = bool(catalog.diagnostics) or any(
            unit.inspection is not None
            and (
                any(
                    d.severity == Severity.ERROR
                    for d in unit.inspection.capability_ir.diagnostics
                )
                or any(
                    a.state == State.AMBIGUOUS
                    for a in unit.inspection.readiness.assessments
                )
            )
            for unit in catalog.sources
        )
        if (catalog.exit_code and not explained_catalog) or (
            not graph.complete
            and not catalog.exit_code
            and not any(d.severity == Severity.ERROR for d in graph.diagnostics)
        ):
            self.global_issues.append(
                self.issue(None, (), None, GraphCode.INPUT, "global")
            )

    @staticmethod
    def issue(
        root: str | None,
        path: tuple[str, ...],
        source: str | None,
        code: GraphCode | CatalogCode | LocalCode,
        reason: Literal[
            "global", "diagnostic", "initialization", "binding", "execution", "import"
        ],
        line: int | None = None,
        column: int | None = None,
    ) -> ScopeIssue:
        return ScopeIssue(root, path, source, line, column, code, reason)

    def owner(self, diagnostic: GraphDiagnostic) -> str:
        # Join canonical source identity to declaration spans. A location inside
        # an unrelated function body is not a module-initialization diagnostic.
        owners = [
            item.capability_id
            for item in self.spans[diagnostic.path]
            if diagnostic.line is not None
            and item.local_readiness.source.line
            <= diagnostic.line
            <= item.local_readiness.source.end_line
        ]
        if len(owners) == 1:
            return owners[0]
        module = self.units[diagnostic.path].module
        assert module is not None
        return module_id(module)

    def neighbors(self, identity: str) -> tuple[str, ...]:
        node = self.nodes.get(identity)
        targets = {edge.target for edge in self.edges[identity] if edge.kind in _FOLLOW}
        if isinstance(node, CapabilityNode):
            targets.add(module_id(node.module))
        elif isinstance(node, ModuleNode):
            parts = node.module.split(".")
            for length in range(1, len(parts)):
                parent = ".".join(parts[:length])
                # Missing parents are explicit synthetic namespaces in the
                # reviewed loader, not missing source that we pretend inspected.
                if parent in self.modules:
                    targets.add(module_id(parent))
        return tuple(
            sorted(
                targets,
                key=lambda target: (
                    not isinstance(self.nodes.get(target), CapabilityNode),
                    target,
                ),
            )
        )

    def paths(self, root: str) -> dict[str, tuple[str, ...]]:
        paths: dict[str, tuple[str, ...]] = {root: (root,)}
        queue = deque([root])
        while queue:
            identity = queue.popleft()
            for target in self.neighbors(identity):
                if target not in paths:
                    paths[target] = (*paths[identity], target)
                    queue.append(target)
        return paths

    def imports_proven(self, identity: str) -> bool:
        edges = self.edges[identity]
        for declaration in self.imports[identity]:
            if declaration.availability != "unconditional" or not declaration.names:
                return False
            for name in declaration.names:
                if name.resolution not in {"module", "capability", "external"}:
                    return False
                kind = {
                    "module": RelationshipKind.MODULE,
                    "capability": RelationshipKind.CAPABILITY,
                    "external": RelationshipKind.EXTERNAL,
                }[name.resolution]
                if not any(
                    edge.kind == kind
                    and edge.target == name.target
                    and edge.path == declaration.path
                    and edge.line == declaration.line
                    and edge.end_line == declaration.end_line
                    and edge.column == declaration.column
                    and edge.end_column == declaration.end_column
                    and edge.availability == declaration.availability
                    for edge in edges
                ):
                    return False
        return True

    def node_issues(
        self, root: str, identity: str, path: tuple[str, ...]
    ) -> list[ScopeIssue]:
        issues = [
            self.issue(
                root,
                path,
                diagnostic.path,
                diagnostic.code,
                "diagnostic",
                diagnostic.line,
                diagnostic.column,
            )
            for diagnostic in self.diagnostics[identity]
        ]
        node = self.nodes.get(identity)
        if not isinstance(node, (CapabilityNode, ModuleNode)):
            assessment = self.assessments.get(identity)
            issues.append(
                self.issue(
                    root,
                    path,
                    assessment.source_path if assessment else None,
                    GraphCode.UNAVAILABLE,
                    "binding",
                )
            )
            return issues
        if not self.imports_proven(identity):
            declaration = next(iter(self.imports[identity]), None)
            issues.append(
                self.issue(
                    root,
                    path,
                    node.path,
                    GraphCode.IMPORT,
                    "import",
                    declaration.line if declaration else None,
                )
            )
        if isinstance(node, CapabilityNode):
            assessment = self.assessments[identity]
            local = assessment.local_readiness
            containment = [
                edge
                for edge in self.edges[module_id(node.module)]
                if edge.kind == RelationshipKind.CONTAINS
                and edge.target == identity
                and edge.path == node.path
                and edge.line == local.source.line
                and edge.end_line == local.source.end_line
            ]
            if len(containment) != 1:
                issues.append(
                    self.issue(
                        root,
                        path,
                        node.path,
                        GraphCode.INPUT,
                        "binding",
                        local.source.line,
                    )
                )
            for edge in self.edges[identity]:
                if (
                    not local.source.line
                    <= edge.line
                    <= edge.end_line
                    <= local.source.end_line
                ):
                    issues.append(
                        self.issue(
                            root,
                            path,
                            node.path,
                            GraphCode.INPUT,
                            "binding",
                            edge.line,
                            edge.column,
                        )
                    )
            if not local.in_ir or local.dimensions.binding.state != State.READY:
                issues.append(
                    self.issue(
                        root,
                        path,
                        node.path,
                        LocalCode.REBOUND,
                        "binding",
                        local.source.line,
                    )
                )
            # Private inputs/outputs do not need a public JSON adapter. Binding
            # and execution still need proof; dependency reasons are checked
            # below with the same exact-import guard introduced in #252.
            for reason in local.dimensions.execution.reasons:
                if reason.code != LocalCode.DEPENDENCY:
                    issues.append(
                        self.issue(
                            root, path, node.path, reason.code, "execution", reason.line
                        )
                    )
        else:
            unit = self.units[node.path]
            reasons = initialization_reasons(unit)
            if not node.analyzed or reasons is None:
                issues.append(
                    self.issue(
                        root, path, node.path, GraphCode.UNAVAILABLE, "initialization"
                    )
                )
            else:
                for reason in reasons:
                    if reason.code != LocalCode.DEPENDENCY:
                        issues.append(
                            self.issue(
                                root,
                                path,
                                node.path,
                                reason.code,
                                "initialization",
                                reason.line,
                            )
                        )
                    elif not any(
                        declaration.line == reason.line
                        for declaration in self.imports[identity]
                    ):
                        issues.append(
                            self.issue(
                                root,
                                path,
                                node.path,
                                reason.code,
                                "initialization",
                                reason.line,
                            )
                        )
            for code in self.catalog_errors[identity]:
                issues.append(self.issue(root, path, node.path, code, "diagnostic"))
            if unit.inspection is not None and any(
                d.severity == Severity.ERROR
                for d in unit.inspection.capability_ir.diagnostics
            ):
                issues.append(
                    self.issue(
                        root, path, node.path, GraphCode.UNAVAILABLE, "initialization"
                    )
                )
        return issues

    def initialization_steps(
        self, identity: str
    ) -> Iterator[tuple[str, str | None, int]]:
        node = self.nodes[identity]
        assert isinstance(node, ModuleNode)
        parts = node.module.split(".")
        for length in range(1, len(parts)):
            parent = module_id(".".join(parts[:length]))
            if parent in self.nodes:
                yield parent, None, 0
        for edge in sorted(
            self.edges[identity],
            key=lambda edge: (
                edge.line,
                edge.column,
                edge.kind == RelationshipKind.CAPABILITY,
                edge.target,
            ),
        ):
            if edge.kind == RelationshipKind.MODULE:
                yield edge.target, None, edge.line
            elif edge.kind == RelationshipKind.CAPABILITY:
                target = self.nodes[edge.target]
                assert isinstance(target, CapabilityNode)
                yield module_id(target.module), edge.target, edge.line

    def initialization_cycles(
        self, root: str, paths: dict[str, tuple[str, ...]]
    ) -> list[ScopeIssue]:
        """Bounded lexical import order; do not certify an early cyclic binding.

        Module-handle cycles can be coherent; importing a callable from an
        active module needs its unconditional definition before that module's
        paused import. Function-body imports run after its module initializes.
        """
        owner = module_id(self.assessments[root].local_readiness.source.module)
        if owner not in paths:
            return []
        starts = [
            owner,
            *sorted(
                node
                for node in paths
                if isinstance(self.nodes.get(node), ModuleNode) and node != owner
            ),
        ]
        done: set[str] = set()
        issues: list[ScopeIssue] = []
        for start in starts:
            if start in done or not isinstance(self.nodes.get(start), ModuleNode):
                continue
            active = {start: 0}
            stack = [(start, self.initialization_steps(start))]
            while stack:
                module, steps = stack[-1]
                step = next(steps, None)
                if step is None:
                    done.add(module)
                    active.pop(module)
                    stack.pop()
                    continue
                target, capability, line = step
                active[module] = line
                if target in active and capability is not None:
                    binding = self.assessments[capability].local_readiness.source
                    if binding.line >= active[target]:
                        node = self.nodes[module]
                        assert isinstance(node, ModuleNode)
                        issues.append(
                            self.issue(
                                root,
                                (*paths[module], capability),
                                node.path,
                                LocalCode.DEPENDENCY,
                                "initialization",
                                line,
                            )
                        )
                if target not in active and target not in done:
                    active[target] = 0
                    stack.append((target, self.initialization_steps(target)))
        return issues

    def root(self, identity: str) -> ScopedRoot:
        paths = self.paths(identity)
        issues = [
            issue
            for node, path in paths.items()
            for issue in self.node_issues(identity, node, path)
        ]
        issues.extend(self.initialization_cycles(identity, paths))
        execution_ready = frozenset(
            node for node in paths if isinstance(self.nodes.get(node), CapabilityNode)
        )
        initialized_modules = frozenset(
            node for node in paths if isinstance(self.nodes.get(node), ModuleNode)
        )
        # All required nodes are checked before optimistic mutual dependency
        # support is used. No invalid root can produce a successful plan.
        refined: dict[str, State] = {}
        for node in sorted(execution_ready):
            assessment = self.assessments[node]
            state = interface_state(
                assessment.local_readiness,
                assessment.source_path,
                assessment.relationships,
                execution_ready=execution_ready,
                initialized_modules=initialized_modules,
                scope_complete=not issues,
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
                        d
                        for d in assessment.relationships.imports
                        if d.line == reason.line
                    ]
                    if not declarations or not all(
                        proven_import(
                            d,
                            assessment.relationships,
                            execution_ready=execution_ready,
                            initialized_modules=initialized_modules,
                        )
                        for d in declarations
                    ):
                        issues.append(
                            self.issue(
                                identity,
                                paths[node],
                                assessment.source_path,
                                reason.code,
                                "import",
                                reason.line,
                            )
                        )
        assessment = self.assessments[identity]
        state = refined.get(identity, assessment.state)
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
    index = _Index(catalog, graph, readiness)
    if any(root not in index.assessments for root in roots):
        raise ValueError("Scope roots must be known readiness identities")
    scoped = {root: index.root(root) for root in sorted(set(roots))}
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
