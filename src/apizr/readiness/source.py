"""Bounded lexical evidence; no imports, evaluation or filesystem discovery."""

import ast
import sys
from collections import defaultdict
from dataclasses import dataclass

Function = ast.FunctionDef | ast.AsyncFunctionDef
TYPING_NAMES = {
    "Any",
    "List",
    "Dict",
    "Tuple",
    "Set",
    "Union",
    "Optional",
    "Literal",
    "Annotated",
    "Callable",
}


def literal_only(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(literal_only(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            k is not None and literal_only(k) and literal_only(v)
            for k, v in zip(node.keys, node.values, strict=True)
        )
    return (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, (ast.UAdd, ast.USub))
        and literal_only(node.operand)
    )


def declaration_expressions(node: Function) -> tuple[ast.expr, ...]:
    args = node.args
    return tuple(
        node.decorator_list
        + args.defaults
        + [e for e in args.kw_defaults if e is not None]
        + [
            a.annotation
            for a in args.posonlyargs + args.args + args.kwonlyargs
            if a.annotation is not None
        ]
        + ([node.returns] if node.returns else [])
    )


def initialization_risk(node: ast.stmt) -> bool:
    if isinstance(node, (ast.Pass, ast.Import, ast.ImportFrom)):
        return False
    if isinstance(node, ast.Expr):
        return not isinstance(node.value, ast.Constant)
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        value = node.value
        return (value is not None and not literal_only(value)) or (
            isinstance(node, ast.AnnAssign)
            and any(isinstance(n, ast.Call) for n in ast.walk(node.annotation))
        )
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return (
            bool(node.decorator_list)
            or any(
                not literal_only(e)
                for e in node.args.defaults
                + [d for d in node.args.kw_defaults if d is not None]
            )
            or any(
                isinstance(n, ast.Call)
                for expression in declaration_expressions(node)
                for n in ast.walk(expression)
            )
        )
    return True


@dataclass(frozen=True)
class Binding:
    name: str
    order: int
    line: int
    node: ast.AST


class SourceFacts(ast.NodeVisitor):
    def __init__(self, tree: ast.Module) -> None:
        self.tree = tree
        self.bindings: dict[str, list[Binding]] = defaultdict(list)
        self.functions: dict[tuple[str, int], Function] = {}
        self.function_orders: dict[tuple[str, int], int] = {}
        self.imports: list[ast.Import | ast.ImportFrom] = []
        self.namespace_lines: list[int] = []
        self.calls: list[ast.Call] = []
        self.import_module_aliases: set[str] = {"import_module", "__import__"}
        self.mutated_roots: set[str] = set()
        self.order = 0
        self.visit(tree)

    def bind(self, name: str, node: ast.AST, line: int) -> None:
        self.order += 1
        self.bindings[name].append(Binding(name, self.order, line, node))

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bind(node.id, node, node.lineno)

    def visit_Attribute(self, node: ast.Attribute | ast.Subscript) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            root = node.value
            while isinstance(root, (ast.Attribute, ast.Subscript)):
                root = root.value
            if isinstance(root, ast.Name):
                self.mutated_roots.add(root.id)
        self.generic_visit(node)

    visit_Subscript = visit_Attribute

    def visit_FunctionDef(self, node: Function) -> None:
        for expression in declaration_expressions(node):
            self.visit(expression)
        self.bind(node.name, node, node.lineno)
        self.functions[node.name, node.lineno] = node
        self.function_orders[node.name, node.lineno] = self.order

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expression in (
            node.decorator_list + node.bases + [k.value for k in node.keywords]
        ):
            self.visit(expression)
        self.bind(node.name, node, node.lineno)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # Defaults execute when creating the lambda; the body does not.
        for expression in node.args.defaults + [
            e for e in node.args.kw_defaults if e is not None
        ]:
            self.visit(expression)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)
            self.visit(node.target)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for target in node.targets:
            self.visit(target)

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.append(node)
        for alias in node.names:
            self.bind(alias.asname or alias.name.split(".")[0], node, node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.imports.append(node)
        for alias in node.names:
            if alias.name == "*":
                self.namespace_lines.append(node.lineno)
            self.bind(alias.asname or alias.name, node, node.lineno)
            if node.module == "importlib" and alias.name == "import_module":
                self.import_module_aliases.add(alias.asname or alias.name)

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append(node)
        if isinstance(node.func, ast.Name) and node.func.id in {
            "globals",
            "locals",
            "vars",
            "exec",
            "eval",
        }:
            self.namespace_lines.append(node.lineno)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.bind(node.name, node, node.lineno)
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self.bind(node.name, node, node.lineno)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self.bind(node.name, node, node.lineno)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self.bind(node.rest, node, node.lineno)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        # Iteration targets have their own scope. Walrus expressions do not.
        self.visit(node.iter)
        for condition in node.ifs:
            self.visit(condition)

    def typing_name(self, node: ast.expr) -> str | None:
        """Recognize syntactic names without trusting shadowed builtin/typing roots."""
        if isinstance(node, ast.Name):
            if node.id in self.mutated_roots:
                return None
            bindings = self.bindings.get(node.id, [])
            if not bindings:
                return node.id
            if len(bindings) == 1 and isinstance(bindings[0].node, ast.ImportFrom):
                imported = bindings[0].node
                if (
                    imported.module == "typing"
                    and imported.level == 0
                    and imported in self.tree.body
                ):
                    for alias in imported.names:
                        if (alias.asname or alias.name) == node.id:
                            return alias.name if alias.name in TYPING_NAMES else None
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in self.mutated_roots or node.attr not in TYPING_NAMES:
                return None
            bindings = self.bindings.get(node.value.id, [])
            if not bindings and node.value.id == "typing":
                return node.attr
            if len(bindings) == 1 and isinstance(bindings[0].node, ast.Import):
                imported = bindings[0].node
                if imported in self.tree.body and any(
                    a.name == "typing" and (a.asname or a.name) == node.value.id
                    for a in imported.names
                ):
                    return node.attr
        return None

    def dynamic_import_lines(self, nodes: tuple[ast.AST, ...]) -> tuple[int, ...]:
        aliases = self.import_module_aliases.copy()
        walked = [child for node in nodes for child in ast.walk(node)]
        for node in walked:
            if isinstance(node, ast.ImportFrom) and node.module == "importlib":
                aliases.update(
                    a.asname or a.name for a in node.names if a.name == "import_module"
                )
        return tuple(
            sorted(
                {
                    node.lineno
                    for node in walked
                    if isinstance(node, ast.Call)
                    and (
                        (isinstance(node.func, ast.Name) and node.func.id in aliases)
                        or (
                            isinstance(node.func, ast.Attribute)
                            and node.func.attr in {"import_module", "__import__"}
                        )
                    )
                }
            )
        )


def unresolved_import(node: ast.Import | ast.ImportFrom) -> bool:
    if isinstance(node, ast.ImportFrom):
        return (
            bool(node.level)
            or (node.module or "").split(".")[0] not in sys.stdlib_module_names
            or any(a.name == "*" for a in node.names)
        )
    return any(
        alias.name.split(".")[0] not in sys.stdlib_module_names for alias in node.names
    )
