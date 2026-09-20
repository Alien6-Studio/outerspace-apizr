"""Bounded iterative lexical scopes. No assignment alias/points-to analysis."""

import ast
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from .model import Availability

Function = ast.FunctionDef | ast.AsyncFunctionDef
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
CONTROL = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.TryStar,
    ast.Match,
    ast.IfExp,
    ast.BoolOp,
)
COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def targets(node: ast.AST) -> set[str]:
    """Only Python binding targets; attribute stores don't create local names."""
    result: set[str] = set()
    pending = [node]
    while pending:
        item = pending.pop()
        if isinstance(item, ast.Name):
            result.add(item.id)
        elif isinstance(item, (ast.Tuple, ast.List)):
            pending.extend(item.elts)
        elif isinstance(item, ast.Starred):
            pending.append(item.value)
    return result


@dataclass(frozen=True)
class Site:
    node: ast.AST
    availability: Availability
    shadows: frozenset[str] = frozenset()


def walk_scope(body: Iterable[ast.AST], *, conditional: bool = False) -> Iterator[Site]:
    """Skip nested scopes entirely; comprehension bindings are expression-local.

    Control-flow children are conservatively conditional. No branch evaluation,
    including the first operand of a boolean expression or loop iterable.
    """
    pending = [(n, conditional, frozenset[str]()) for n in reversed(tuple(body))]
    while pending:
        node, under_control, shadows = pending.pop()
        yield Site(node, "conditional" if under_control else "unconditional", shadows)
        if isinstance(node, SCOPES) or type(node).__name__ == "TypeAlias":
            continue
        if isinstance(node, COMPREHENSIONS):
            names = frozenset(
                name for g in node.generators for name in targets(g.target)
            )
            shadows = shadows | names
            under_control = True
        if isinstance(node, CONTROL):
            under_control = True
        pending.extend(
            (child, under_control, shadows)
            for child in reversed(list(ast.iter_child_nodes(node)))
        )


@dataclass
class Inventory:
    writes: dict[str, list[ast.AST]] = field(default_factory=lambda: defaultdict(list))
    globals: set[str] = field(default_factory=set[str])
    nonlocals: set[str] = field(default_factory=set[str])
    star: bool = False


def inventory(sites: tuple[Site, ...], function: Function | None = None) -> Inventory:
    result = Inventory()
    if function is not None:
        # Generic type parameters introduce an annotation scope visible to the
        # function body on Python >=3.12. Avoid referencing newer AST classes.
        for child in ast.iter_child_nodes(function):
            if type(child).__name__ in {"TypeVar", "ParamSpec", "TypeVarTuple"}:
                name = getattr(child, "name", None)
                if isinstance(name, str):
                    result.writes[name].append(child)
        args = function.args
        for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
            result.writes[arg.arg].append(arg)
        for arg in (args.vararg, args.kwarg):
            if arg is not None:
                result.writes[arg.arg].append(arg)
    for site in sites:
        node = site.node
        names: set[str] = set()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            names.update(
                alias.asname or alias.name.split(".")[0] for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            result.star |= any(alias.name == "*" for alias in node.names)
            names.update(
                alias.asname or alias.name for alias in node.names if alias.name != "*"
            )
        elif isinstance(node, (ast.Assign, ast.Delete)):
            for target in node.targets:
                names.update(targets(target))
        elif type(node).__name__ == "TypeAlias":
            # PEP 695 on Python >=3.12; no dependency on newer AST classes.
            target = getattr(node, "name", None)
            if isinstance(target, ast.Name):
                names.add(target.id)
        elif isinstance(node, ast.AnnAssign):
            if function is not None or node.value is not None:
                names.update(targets(node.target))
        elif isinstance(node, (ast.AugAssign, ast.NamedExpr)):
            names.update(targets(node.target))
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            names.update(targets(node.target))
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            names.update(targets(node.optional_vars))
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            names.add(node.rest)
        elif isinstance(node, ast.Global):
            result.globals.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            result.nonlocals.update(node.names)
        # Comprehension targets do not leak. Named expressions DO bind their
        # containing scope even when the target also appears in a shadow set.
        if not isinstance(node, ast.NamedExpr):
            names.difference_update(site.shadows)
        for name in sorted(names):
            result.writes[name].append(node)
    return result


def dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([node.id, *reversed(parts)])
