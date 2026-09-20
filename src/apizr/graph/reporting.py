"""Bounded human output, separate from the canonical graph artifact."""

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel
from apizr.repository.serialization import canonical_bytes

from .model import Graph, Statistics
from .serialization import graph_digest


class Envelope(ValueModel):
    graph: Graph
    graph_digest: Digest
    statistics: Statistics


def envelope_bytes(graph: Graph) -> bytes:
    # These derived values deliberately stay outside canonical Graph v1.
    return canonical_bytes(
        Envelope(
            graph=graph, graph_digest=graph_digest(graph), statistics=graph.statistics
        )
    )


def text_report(graph: Graph, *, details: bool = False) -> str:
    stats = graph.statistics
    lines = [
        "Apizr capability graph (static evidence, not runtime execution)",
        "",
        f"Modules: {stats.modules}",
        f"Capabilities: {stats.capabilities}",
        f"External modules: {stats.external_modules}",
        *(f"{kind.value}: {count}" for kind, count in stats.relationships.items()),
        f"Diagnostics: {stats.diagnostics}",
        f"Complete: {str(graph.complete).lower()}",
        "",
    ]
    relationships = graph.relationships if details else graph.relationships[:20]
    for edge in relationships:
        lines.append(
            f"{edge.source} --{edge.kind.value}--> {edge.target} ({edge.path!r}:{edge.line}:{edge.column}, {edge.availability})"
        )
    if len(relationships) < len(graph.relationships):
        lines.append("Further relationships omitted; use --details.")
    diagnostics = graph.diagnostics if details else graph.diagnostics[:10]
    for diagnostic in diagnostics:
        lines.append(
            f"{diagnostic.code.value} {diagnostic.path!r}:{diagnostic.line or 0}: {diagnostic.message}"
        )
    if len(diagnostics) < len(graph.diagnostics):
        lines.append("Further diagnostics omitted; use --details.")
    if graph.catalog_exit_code:
        lines.append(
            "Catalog has blocking diagnostics; use apizr scan --details for source inspection details."
        )
    return "\n".join(lines) + "\n"
