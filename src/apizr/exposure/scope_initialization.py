"""Iterative lexical import-order proof over the selected dependency closure."""

from collections.abc import Iterator

from apizr.graph.model import CapabilityNode, ModuleNode, RelationshipKind, module_id
from apizr.readiness.model import Code as LocalCode

from .scope_index import EvidenceIndex
from .scope_model import ScopeIssue


def initialization_steps(
    index: EvidenceIndex, identity: str
) -> Iterator[tuple[str, str | None, int]]:
    node = index.nodes[identity]
    assert isinstance(node, ModuleNode)
    parts = node.module.split(".")
    for length in range(1, len(parts)):
        parent = module_id(".".join(parts[:length]))
        if parent in index.nodes:
            yield parent, None, 0
    for edge in sorted(
        index.edges[identity],
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
            target = index.nodes[edge.target]
            assert isinstance(target, CapabilityNode)
            yield module_id(target.module), edge.target, edge.line


def initialization_cycles(
    index: EvidenceIndex, root: str, paths: dict[str, tuple[str, ...]]
) -> list[ScopeIssue]:
    """Bounded lexical import order; do not certify an early cyclic binding.

    Module-handle cycles can be coherent; importing a callable from an
    active module needs its unconditional definition before that module's
    paused import. Function-body imports run after its module initializes.
    """
    owner = module_id(index.assessments[root].local_readiness.source.module)
    if owner not in paths:
        return []
    starts = [
        owner,
        *sorted(
            node
            for node in paths
            if isinstance(index.nodes.get(node), ModuleNode) and node != owner
        ),
    ]
    done: set[str] = set()
    issues: list[ScopeIssue] = []
    for start in starts:
        if start in done or not isinstance(index.nodes.get(start), ModuleNode):
            continue
        active = {start: 0}
        stack = [(start, initialization_steps(index, start))]
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
                binding = index.assessments[capability].local_readiness.source
                if binding.line >= active[target]:
                    node = index.nodes[module]
                    assert isinstance(node, ModuleNode)
                    issues.append(
                        index.issue(
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
                stack.append((target, initialization_steps(index, target)))
    return issues
