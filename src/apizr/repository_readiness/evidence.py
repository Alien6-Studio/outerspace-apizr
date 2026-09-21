"""Project only existing Graph facts; never parse, resolve or propagate effects."""

from apizr.capabilities.model import Effects
from apizr.graph.model import (
    CapabilityNode,
    Code,
    Graph,
    ModuleNode,
    RelationshipKind,
    module_id,
)
from apizr.readiness.model import Assessment
from apizr.repository.model import Catalog

from .model import Dependency, Relationships


def validate_linkage(catalog: Catalog, graph: Graph) -> None:
    """Digests bind artifacts; also check redundant graph metadata against Catalog."""
    from apizr.repository.serialization import catalog_digest

    if (
        graph.catalog_digest != catalog_digest(catalog)
        or graph.repository_digest != catalog.repository_digest
    ):
        raise ValueError("Graph/Catalog digest linkage mismatch")
    if graph.catalog_exit_code != catalog.exit_code:
        raise ValueError("Graph/Catalog exit evidence mismatch")
    expected = {
        c.id: CapabilityNode(
            id=c.id,
            module=c.module,
            name=c.span.symbol,
            path=c.source_path,
            readiness=c.readiness,
            can_generate_interface=c.can_generate_interface,
            execution=c.execution,
        )
        for c in catalog.capabilities
    }
    if {n.id: n for n in graph.nodes if isinstance(n, CapabilityNode)} != expected:
        raise ValueError("Graph capability metadata disagrees with Catalog")
    groups: dict[str, list[str]] = {}
    for source in catalog.sources:
        if source.module is not None:
            groups.setdefault(source.module, []).append(source.path)
    modules = {n.module: n.path for n in graph.nodes if isinstance(n, ModuleNode)}
    if modules != {name: paths[0] for name, paths in groups.items() if len(paths) == 1}:
        raise ValueError("Graph module metadata disagrees with Catalog")


def relationship_evidence(
    assessment: Assessment,
    path: str,
    in_catalog: bool,
    graph: Graph,
    local: dict[str, Assessment],
    effects: dict[str, Effects],
) -> Relationships:
    if not in_catalog:
        return Relationships(state="unavailable")
    identity = assessment.capability_id
    module = module_id(assessment.source.module)
    spans = [
        a.source for a in local.values() if a.source.module == assessment.source.module
    ]
    # Graph v1 has no diagnostic scope field. A location within a declaration
    # affects that declaration; outside every declaration it affects the module.
    diagnostics = tuple(
        d
        for d in graph.diagnostics
        if (d.path == "." and d.code == Code.LIMIT)
        or (
            d.path == path
            and (
                d.line is None
                or assessment.source.line <= d.line <= assessment.source.end_line
                or not any(s.line <= d.line <= s.end_line for s in spans)
            )
        )
    )
    direct = tuple(r for r in graph.relationships if r.source == identity)
    module_imports = tuple(
        r
        for r in graph.relationships
        if r.source == module
        and r.kind
        in {
            RelationshipKind.MODULE,
            RelationshipKind.EXTERNAL,
            RelationshipKind.CAPABILITY,
        }
    )
    imports = tuple(d for d in graph.imports if d.source in {identity, module})
    targets = sorted(
        {
            r.target
            for r in (*direct, *module_imports)
            if r.kind
            in {
                RelationshipKind.CALL,
                RelationshipKind.REFERENCE,
                RelationshipKind.CAPABILITY,
            }
        }
    )
    dependencies = tuple(
        Dependency(capability_id=t, local_readiness=local[t], effects=effects[t])
        for t in targets
    )
    node = next((n for n in graph.nodes if n.id == module), None)
    unavailable = (
        not isinstance(node, ModuleNode)
        or not node.analyzed
        or any(
            d.code in {Code.INPUT, Code.LIMIT, Code.UNAVAILABLE} for d in diagnostics
        )
    )
    partial = bool(diagnostics) or any(
        n.resolution in {"unresolved", "ambiguous", "star"}
        for d in imports
        for n in d.names
    )
    return Relationships(
        state="unavailable" if unavailable else "partial" if partial else "resolved",
        diagnostics=diagnostics,
        direct=direct,
        module_imports=module_imports,
        imports=imports,
        dependencies=dependencies,
    )
