"""Conservative correlation of existing metric signals with direct global bindings."""

import ast
from collections import Counter

from apizr.experiments._lexical import bounded_tree
from apizr.experiments.metrics import MetricDiscoveryResult
from apizr.experiments.planning import MetricBinding


def automatic_metrics(
    source: str | bytes, discovered: MetricDiscoveryResult
) -> tuple[MetricBinding, ...]:
    """Reuse signal authority; no second framework resolver or expression evaluator.

    Only direct single-name assignments qualify. Any other syntactic binding of
    that name (even in a nested scope) refuses automatic attribution. Dynamic
    namespace mutation and later uses of the result are conservatively excluded.
    Explicit selectors remain available for these cases.
    """
    tree = bounded_tree(source)
    nodes = tuple(ast.walk(tree))
    if any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id in {"exec", "eval", "globals", "locals", "vars"}
        for n in nodes
    ):
        return ()
    writes: Counter[str] = Counter()
    for node in nodes:
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            writes[node.id] += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            writes[node.name] += 1
        elif isinstance(node, ast.alias):
            writes[node.asname or node.name.split(".")[0]] += 1
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            writes.update(node.names)
        elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
            if node.name is not None:
                writes[node.name] += 1
        elif isinstance(node, ast.MatchMapping) and node.rest is not None:
            writes[node.rest] += 1
    counts = Counter(signal.name for signal in discovered.signals)
    signals = {(s.line, s.column): s for s in discovered.signals}
    bindings: list[MetricBinding] = []
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target, value = statement.targets[0], statement.value
        elif isinstance(statement, ast.AnnAssign):
            target, value = statement.target, statement.value
        else:
            continue
        if not isinstance(target, ast.Name) or not isinstance(value, ast.Call):
            continue
        signal = signals.get((value.lineno, value.col_offset))
        if signal is None or counts[signal.name] != 1 or writes[target.id] != 1:
            continue
        if any(
            isinstance(n, ast.Name)
            and n.id == target.id
            and isinstance(n.ctx, ast.Load)
            and (n.lineno, n.col_offset) > (value.lineno, value.col_offset)
            for n in nodes
        ):
            continue
        bindings.append(MetricBinding(name=signal.name, binding=target.id))
    return tuple(sorted(bindings, key=lambda item: item.name))
