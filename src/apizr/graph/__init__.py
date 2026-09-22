"""Conservative static relationships over a digest-bound Capability Catalog."""

from .analysis import GraphInputError
from .builder import (
    RepositoryEvidence,
    RepositoryGraph,
    analyze_repository,
    build_graph,
    graph_repository,
)
from .model import Code, Graph, RelationshipKind
from .policy import GraphPolicy
from .serialization import graph_bytes, graph_digest, policy_bytes, policy_digest

__all__ = [
    "GraphInputError",
    "RepositoryGraph",
    "RepositoryEvidence",
    "analyze_repository",
    "build_graph",
    "graph_repository",
    "Code",
    "Graph",
    "RelationshipKind",
    "GraphPolicy",
    "graph_bytes",
    "graph_digest",
    "policy_bytes",
    "policy_digest",
]
