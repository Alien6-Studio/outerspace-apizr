"""Index complete evidence and traverse deterministic required-dependency paths.

Global admission concerns the full retained manifest. Traversal never follows
containment as a dependency and never prunes the original audit.
"""

from collections import defaultdict, deque
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
from apizr.graph.model import Code as GraphCode
from apizr.graph.model import Diagnostic as GraphDiagnostic
from apizr.readiness.model import Code as LocalCode
from apizr.readiness.model import State
from apizr.repository.model import Catalog
from apizr.repository.model import Code as CatalogCode
from apizr.repository_readiness.model import (
    DeclarationAssessment,
    RepositoryReadinessReport,
)

from .scope_model import ScopeIssue

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


class EvidenceIndex:
    def __init__(
        self, catalog: Catalog, graph: Graph, report: RepositoryReadinessReport
    ):
        self.nodes = {node.id: node for node in graph.nodes}
        self.units = {unit.path: unit for unit in catalog.sources}
        self.modules = {
            unit.module: unit for unit in catalog.sources if unit.module is not None
        }
        self.assessments = {item.capability_id: item for item in report.assessments}
        self.external_modules = frozenset(
            module
            for wheel in report.policy.dependency_wheels
            for module in wheel.modules
        )
        self.edges: dict[str, list[Relationship]] = defaultdict(list)
        self.imports: dict[str, list[ImportDeclaration]] = defaultdict(list)
        self.diagnostics: dict[str, list[GraphDiagnostic]] = defaultdict(list)
        self.catalog_errors: dict[str, list[CatalogCode]] = defaultdict(list)
        self.spans: dict[str, list[DeclarationAssessment]] = defaultdict(list)
        self.global_issues: list[ScopeIssue] = []
        if any(
            module.split(".")[0] in {name.split(".")[0] for name in self.modules}
            for module in self.external_modules
        ):
            self.global_issues.append(
                self.issue(None, (), None, GraphCode.COLLISION, "global")
            )
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
