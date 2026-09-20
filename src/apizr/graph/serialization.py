"""Canonical UTF-8 JSON with independent policy/graph content identities."""

from typing import TYPE_CHECKING

from apizr.capabilities.model import Digest
from apizr.repository.serialization import canonical_bytes

from .policy import GraphPolicy

if TYPE_CHECKING:
    from .model import Graph


def policy_bytes(policy: GraphPolicy) -> bytes:
    return canonical_bytes(GraphPolicy.model_validate(policy.model_dump(mode="json")))


def policy_digest(policy: GraphPolicy) -> Digest:
    return Digest.of_bytes(policy_bytes(policy))


def graph_bytes(graph: "Graph") -> bytes:
    from .model import Graph

    return canonical_bytes(Graph.model_validate(graph.model_dump(mode="json")))


def graph_digest(graph: "Graph") -> Digest:
    return Digest.of_bytes(graph_bytes(graph))
