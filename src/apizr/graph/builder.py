"""Digest-bound Catalog consumer and single-discovery repository orchestration."""

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from apizr.capabilities.model import Digest, Severity
from apizr.readiness import State
from apizr.repository import Catalog, ScanPolicy, SourceUnit, catalog_digest
from apizr.repository.discovery import discover
from apizr.repository.scanner import assemble

from .analysis import Analysis, GraphInputError, Index, LimitError, location
from .bindings import Inventory, Site, inventory, walk_scope
from .calls import analyze_calls
from .imports import binding_map, declarations, stable_bindings, symbol_inventory
from .model import (
    CapabilityNode,
    Code,
    Diagnostic,
    Graph,
    ModuleNode,
    Node,
    RelationshipKind,
    module_id,
)
from .policy import GraphPolicy
from .serialization import policy_digest


def validated_inputs(catalog: Catalog, sources: Mapping[str, bytes]) -> Catalog:
    catalog = Catalog.model_validate(catalog.model_dump(mode="json"))
    expected = {s.path: s for s in catalog.sources if s.inspection is not None}
    if set(sources) != set(expected):
        raise GraphInputError(
            "APIZR-GRAPH-001: source keys must exactly match inspected catalog units"
        )
    for path, unit in expected.items():
        _check_content(sources[path], unit)
    return catalog


def _check_content(content: object, unit: SourceUnit) -> None:
    if (
        not isinstance(content, bytes)
        or len(content) != unit.size
        or Digest.of_bytes(content) != unit.source_digest
    ):
        raise GraphInputError(
            "APIZR-GRAPH-001: source bytes do not match catalog digest/size"
        )


def catalog_facts(
    catalog: Catalog, policy: GraphPolicy, *, analyzed: bool = True
) -> Analysis:
    groups: dict[str, list[SourceUnit]] = {}
    for source in catalog.sources:
        if source.module is not None:
            groups.setdefault(source.module, []).append(source)
    modules = {name: group[0] for name, group in groups.items() if len(group) == 1}
    collisions = {name for name, group in groups.items() if len(group) > 1}
    nodes: dict[str, Node] = {
        module_id(name): ModuleNode(
            id=module_id(name),
            module=name,
            path=source.path,
            analyzed=analyzed and source.inspection is not None,
        )
        for name, source in modules.items()
    }
    stable = {
        a.capability_id
        for s in catalog.sources
        if s.inspection
        for a in s.inspection.readiness.assessments
        if a.in_ir and a.dimensions.binding.state == State.READY
    }
    capabilities = {(c.module, c.span.symbol): c for c in catalog.capabilities}
    for capability in catalog.capabilities:
        nodes[capability.id] = CapabilityNode(
            id=capability.id,
            module=capability.module,
            name=capability.span.symbol,
            path=capability.source_path,
            readiness=capability.readiness,
            can_generate_interface=capability.can_generate_interface,
            execution=capability.execution,
        )
    analysis = Analysis(policy, Index(modules, collisions, capabilities, stable), nodes)
    for source in catalog.sources:
        if source.module in collisions:
            analysis.diagnostics.add(Diagnostic(code=Code.COLLISION, path=source.path))
        elif source.inspection is None:
            analysis.diagnostics.add(
                Diagnostic(code=Code.UNAVAILABLE, path=source.path)
            )
    return analysis


def build_graph(
    catalog: Catalog, sources: Mapping[str, bytes], *, policy: GraphPolicy | None = None
) -> Graph:
    """Require exactly successful Inspection source units, no extra/missing paths.

    No source imports, environment resolution, filesystem access or execution.
    All syntax relationships are discarded on aggregate resource exhaustion.
    """
    sources = dict(sources)
    catalog = validated_inputs(catalog, sources)
    selected = (
        GraphPolicy()
        if policy is None
        else GraphPolicy.model_validate(policy.model_dump(mode="json"))
    )
    analysis = catalog_facts(catalog, selected)
    try:
        trees: dict[str, tuple[Site, ...]] = {}
        inventories: dict[str, Inventory] = {}
        # Count every AST node/call/import, including ignored nested scopes,
        # before retaining a scope index. Only one tree is allocated per source.
        for module, unit in sorted(analysis.index.modules.items()):
            if unit.inspection is None:
                continue
            tree = ast.parse(sources[unit.path], filename="<apizr-graph>")
            analysis.count_tree(tree)
            sites = tuple(walk_scope(tree.body))
            trees[module] = sites
            inventories[module] = inventory(sites)
            analysis.index.symbols[module] = symbol_inventory(
                inventories[module], module, unit.is_package
            )
        definitions = {
            (module, site.node.name, site.node.lineno): site
            for module, sites in trees.items()
            for site in sites
            if isinstance(site.node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for capability in catalog.capabilities:
            site = definitions.get(
                (capability.module, capability.span.symbol, capability.span.line)
            )
            if site is None:
                raise GraphInputError(
                    "APIZR-GRAPH-001: catalog capability span has no matching source declaration"
                )
            analysis.edge(
                module_id(capability.module),
                capability.id,
                RelationshipKind.CONTAINS,
                location(capability.source_path, site),
            )
        for module, sites in sorted(trees.items()):
            unit = analysis.index.modules[module]
            module_inventory = inventories[module]
            imported = declarations(
                analysis,
                sites,
                module=module,
                path=unit.path,
                is_package=unit.is_package,
                source=module_id(module),
                scope="module_scope",
            )
            stable = binding_map(
                stable_bindings(imported, module_inventory, analysis, unit.path)
            )
            analyze_calls(
                analysis,
                sites,
                module=module,
                path=unit.path,
                caller=None,
                local=Inventory(),
                module_inventory=module_inventory,
                local_imports={},
                module_imports=stable,
            )
            for site in sites:
                definition = site.node
                if not isinstance(definition, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                capability = analysis.index.capabilities.get((module, definition.name))
                if capability is None or capability.span.line != definition.lineno:
                    continue
                body = tuple(
                    walk_scope(
                        definition.body, conditional=site.availability == "conditional"
                    )
                )
                local = inventory(body, definition)
                local_imports = declarations(
                    analysis,
                    body,
                    module=module,
                    path=unit.path,
                    is_package=unit.is_package,
                    source=capability.id,
                    scope="capability_scope",
                )
                local_stable = stable_bindings(
                    local_imports, local, analysis, unit.path
                )
                analyze_calls(
                    analysis,
                    body,
                    module=module,
                    path=unit.path,
                    caller=capability.id,
                    local=local,
                    module_inventory=module_inventory,
                    local_imports=binding_map(local_stable),
                    module_imports=stable,
                )
    except (RecursionError, SyntaxError) as error:
        # Catalog inspection is authoritative. Parser implementation limits must
        # not produce a contradictory partial graph or leak source snippets.
        if isinstance(error, SyntaxError):
            raise GraphInputError(
                "APIZR-GRAPH-001: inspected source cannot be parsed consistently"
            ) from None
        analysis = catalog_facts(catalog, selected, analyzed=False)
        analysis.diagnostics.add(Diagnostic(code=Code.LIMIT, path=".", limit="parser"))
    except LimitError as error:
        analysis = catalog_facts(catalog, selected, analyzed=False)
        analysis.diagnostics.add(
            Diagnostic(code=Code.LIMIT, path=".", limit=error.limit)
        )
    complete = not catalog.exit_code and not any(
        d.severity == Severity.ERROR for d in analysis.diagnostics
    )
    return Graph(
        catalog_digest=catalog_digest(catalog),
        repository_digest=catalog.repository_digest,
        graph_policy=selected,
        graph_policy_digest=policy_digest(selected),
        catalog_exit_code=1 if catalog.exit_code else 0,
        complete=complete,
        nodes=tuple(analysis.nodes.values()),
        relationships=tuple(analysis.relationships),
        imports=tuple(analysis.imports),
        diagnostics=tuple(analysis.diagnostics),
    )


@dataclass(frozen=True)
class RepositoryGraph:
    catalog: Catalog
    graph: Graph


@dataclass(frozen=True)
class RepositoryEvidence(RepositoryGraph):
    """Noncanonical session retaining the exact bounded discovery bytes."""

    sources: Mapping[str, bytes]


def analyze_repository(
    root: str | Path,
    *,
    scan_policy: ScanPolicy | None = None,
    graph_policy: GraphPolicy | None = None,
) -> RepositoryEvidence:
    """One bounded discovery; Catalog and Graph consume the SAME source bytes."""
    selected = (
        ScanPolicy()
        if scan_policy is None
        else ScanPolicy.model_validate(scan_policy.model_dump(mode="json"))
    )
    manifest, diagnostics = discover(root, selected)
    catalog = assemble(manifest, selected, diagnostics)
    paths = {s.path for s in catalog.sources if s.inspection is not None}
    sources = {
        s.path: s.content for s in manifest if s.path in paths and s.content is not None
    }
    return RepositoryEvidence(
        catalog,
        build_graph(catalog, sources, policy=graph_policy),
        MappingProxyType(sources),
    )


def graph_repository(
    root: str | Path,
    *,
    scan_policy: ScanPolicy | None = None,
    graph_policy: GraphPolicy | None = None,
) -> RepositoryGraph:
    """Compatible Catalog/Graph API; callers needing bytes use analyze_repository."""
    evidence = analyze_repository(
        root, scan_policy=scan_policy, graph_policy=graph_policy
    )
    return RepositoryGraph(evidence.catalog, evidence.graph)
