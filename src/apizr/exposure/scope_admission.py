"""Prove exact imports, callable bindings and required module initialization."""

from apizr.capabilities.model import Severity
from apizr.graph.model import CapabilityNode, ModuleNode, RelationshipKind, module_id
from apizr.graph.model import Code as GraphCode
from apizr.readiness.model import Code as LocalCode
from apizr.readiness.model import State
from apizr.repository_readiness.initialization import initialization_reasons

from .scope_index import EvidenceIndex
from .scope_model import ScopeIssue


def imports_proven(index: EvidenceIndex, identity: str) -> bool:
    edges = index.edges[identity]
    for declaration in index.imports[identity]:
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
    index: EvidenceIndex, root: str, identity: str, path: tuple[str, ...]
) -> list[ScopeIssue]:
    issues = [
        index.issue(
            root,
            path,
            diagnostic.path,
            diagnostic.code,
            "diagnostic",
            diagnostic.line,
            diagnostic.column,
        )
        for diagnostic in index.diagnostics[identity]
    ]
    node = index.nodes.get(identity)
    if not isinstance(node, (CapabilityNode, ModuleNode)):
        assessment = index.assessments.get(identity)
        issues.append(
            index.issue(
                root,
                path,
                assessment.source_path if assessment else None,
                GraphCode.UNAVAILABLE,
                "binding",
            )
        )
        return issues
    if not imports_proven(index, identity):
        declaration = next(iter(index.imports[identity]), None)
        issues.append(
            index.issue(
                root,
                path,
                node.path,
                GraphCode.IMPORT,
                "import",
                declaration.line if declaration else None,
            )
        )
    if isinstance(node, CapabilityNode):
        assessment = index.assessments[identity]
        local = assessment.local_readiness
        containment = [
            edge
            for edge in index.edges[module_id(node.module)]
            if edge.kind == RelationshipKind.CONTAINS
            and edge.target == identity
            and edge.path == node.path
            and edge.line == local.source.line
            and edge.end_line == local.source.end_line
        ]
        if len(containment) != 1:
            issues.append(
                index.issue(
                    root,
                    path,
                    node.path,
                    GraphCode.INPUT,
                    "binding",
                    local.source.line,
                )
            )
        for edge in index.edges[identity]:
            if (
                not local.source.line
                <= edge.line
                <= edge.end_line
                <= local.source.end_line
            ):
                issues.append(
                    index.issue(
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
                index.issue(
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
                    index.issue(
                        root, path, node.path, reason.code, "execution", reason.line
                    )
                )
    else:
        unit = index.units[node.path]
        reasons = initialization_reasons(unit)
        if not node.analyzed or reasons is None:
            issues.append(
                index.issue(
                    root, path, node.path, GraphCode.UNAVAILABLE, "initialization"
                )
            )
        else:
            for reason in reasons:
                if reason.code != LocalCode.DEPENDENCY:
                    issues.append(
                        index.issue(
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
                    for declaration in index.imports[identity]
                ):
                    issues.append(
                        index.issue(
                            root,
                            path,
                            node.path,
                            reason.code,
                            "initialization",
                            reason.line,
                        )
                    )
        for code in index.catalog_errors[identity]:
            issues.append(index.issue(root, path, node.path, code, "diagnostic"))
        if unit.inspection is not None and any(
            d.severity == Severity.ERROR
            for d in unit.inspection.capability_ir.diagnostics
        ):
            issues.append(
                index.issue(
                    root, path, node.path, GraphCode.UNAVAILABLE, "initialization"
                )
            )
    return issues
