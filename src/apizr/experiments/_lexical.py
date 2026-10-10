"""Internal lexical authority shared by bounded experiment source producers."""

import ast
from collections import Counter
from collections.abc import Callable, Iterable
from typing import cast


class _Bindings(ast.NodeVisitor):
    """Lexical writes, without descending into nested execution scopes."""

    def __init__(self) -> None:
        self.writes: Counter[str] = Counter()
        self.star = False

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.writes[node.id] += 1

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                self.writes[root.id] += 1
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        self.writes.update(
            alias.asname or alias.name.split(".")[0] for alias in node.names
        )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.star |= any(alias.name == "*" for alias in node.names)
        self.writes.update(alias.asname or alias.name for alias in node.names)

    def visit_Global(self, node: ast.Global | ast.Nonlocal) -> None:
        self.writes.update(node.names)

    visit_Nonlocal = visit_Global

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.writes[node.name] += 1
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs | ast.MatchStar) -> None:
        if node.name:
            self.writes[node.name] += 1
        self.generic_visit(node)

    visit_MatchStar = visit_MatchAs

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self.writes[node.rest] += 1
        self.generic_visit(node)

    def visit_FunctionDef(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    ) -> None:
        self.writes[node.name] += 1
        # Defaults/decorators can bind names in the containing scope. Conservative
        # annotation scanning also covers version-dependent annotation evaluation.
        for field, value in ast.iter_fields(node):
            if field != "body":
                if isinstance(value, ast.AST):
                    self.visit(value)
                elif isinstance(value, list):
                    for child in cast(list[ast.AST], value):
                        self.visit(child)

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.visit(node.args)

    def visit_arg(self, node: ast.arg) -> None:
        # Parameters are collected explicitly only for their own lexical scope.
        if node.annotation:
            self.visit(node.annotation)


def _scope(
    body: Iterable[ast.AST],
    inherited: dict[str, tuple[str, tuple[int, int]]],
    parameters: ast.arguments | None,
    modules: frozenset[str],
    members: Callable[[str], bool],
) -> dict[str, tuple[str, tuple[int, int]]]:
    body = tuple(body)
    collector = _Bindings()
    for node in body:
        collector.visit(node)
        # An explicit nested global/nonlocal declaration or attribute write makes
        # enclosing authority uncertain, even before a later call to that scope.
        for nested in ast.walk(node):
            if isinstance(nested, (ast.Global, ast.Nonlocal)):
                collector.writes.update(nested.names)
            elif isinstance(nested, ast.Attribute) and isinstance(
                nested.ctx, (ast.Store, ast.Del)
            ):
                collector.visit_Attribute(nested)
    if parameters is not None:
        collector.writes.update(
            arg.arg for arg in ast.walk(parameters) if isinstance(arg, ast.arg)
        )
    bindings = (
        {}
        if collector.star
        else {
            name: value
            for name, value in inherited.items()
            if name not in collector.writes
        }
    )
    if collector.star:
        return bindings
    for node in body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name
                if alias.name in modules and collector.writes[name] == 1:
                    bindings[name] = (alias.name, (node.lineno, node.col_offset))
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            for alias in node.names:
                name = alias.asname or alias.name
                qualified = f"{node.module}.{alias.name}"
                if members(qualified) and collector.writes[name] == 1:
                    bindings[name] = (qualified, (node.lineno, node.col_offset))
    return bindings


class LexicalVisitor(ast.NodeVisitor):
    """Conservative scopes; the consumer supplies its exact import allowlist."""

    def __init__(self, modules: frozenset[str], members: Callable[[str], bool]) -> None:
        self.modules = modules
        self.members = members
        self.bindings: dict[str, tuple[str, tuple[int, int]]] = {}
        self.function_parent: dict[str, tuple[str, tuple[int, int]]] = {}

    def scope(
        self,
        body: Iterable[ast.AST],
        inherited: dict[str, tuple[str, tuple[int, int]]],
        parameters: ast.arguments | None = None,
    ) -> dict[str, tuple[str, tuple[int, int]]]:
        return _scope(body, inherited, parameters, self.modules, self.members)

    def visit_Module(self, node: ast.Module) -> None:
        self.bindings = self.scope(node.body, {})
        self.function_parent = self.bindings
        self.generic_visit(node)

    def visit_FunctionDef(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    ) -> None:
        # PEP 695 type-parameter scopes are outside this initial recognizer.
        # Ignoring the whole generic definition avoids trusting a shadowed name
        # in annotations/defaults as well as in its body, on Python 3.12+.
        if getattr(node, "type_params", ()):
            return
        old, parent = self.bindings, self.function_parent
        # Calls in decorators/defaults/bases belong to the outer scope.
        for field, value in ast.iter_fields(node):
            if field != "body":
                if isinstance(value, ast.AST):
                    self.visit(value)
                elif isinstance(value, list):
                    for child in cast(list[ast.AST], value):
                        self.visit(child)
        is_class = isinstance(node, ast.ClassDef)
        self.bindings = self.scope(node.body, parent, None if is_class else node.args)
        if not is_class:
            self.function_parent = self.bindings
        for child in node.body:
            self.visit(child)
        self.bindings, self.function_parent = old, parent

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.visit(node.args)
        old, parent = self.bindings, self.function_parent
        self.bindings = self.scope((node.body,), parent, node.args)
        self.function_parent = self.bindings
        self.visit(node.body)
        self.bindings, self.function_parent = old, parent

    def visit_ListComp(
        self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
    ) -> None:
        old, parent = self.bindings, self.function_parent
        self.bindings = self.scope((node,), parent)
        self.function_parent = self.bindings
        self.generic_visit(node)
        self.bindings, self.function_parent = old, parent

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def resolve_call(self, node: ast.Call) -> str:
        qualified = ""
        if isinstance(node.func, ast.Name):
            binding = self.bindings.get(node.func.id)
            if binding is not None and (node.lineno, node.col_offset) > binding[1]:
                qualified = binding[0]
        elif isinstance(node.func, ast.Attribute) and isinstance(
            node.func.value, ast.Name
        ):
            binding = self.bindings.get(node.func.value.id)
            if binding is not None and (node.lineno, node.col_offset) > binding[1]:
                qualified = f"{binding[0]}.{node.func.attr}"
        return qualified
