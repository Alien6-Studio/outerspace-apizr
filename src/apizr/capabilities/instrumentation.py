"""Source-only SDK binding evidence; never import the SDK or evaluate source."""

import ast
from collections import defaultdict

Function = ast.FunctionDef | ast.AsyncFunctionDef
SDK_MEMBERS = frozenset(
    {
        "experiment",
        "session",
        "log_parameter",
        "log_input",
        "log_metric",
        "log_artifact",
    }
)


def own_yield(function: Function) -> bool:
    """Identify generator syntax in this function, excluding nested scopes."""
    pending: list[ast.AST] = list(function.body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            # Defaults execute in this outer function, unlike the nested body.
            pending.extend(node.args.defaults)
            pending.extend(d for d in node.args.kw_defaults if d is not None)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                pending.extend(node.decorator_list)
        elif isinstance(node, ast.ClassDef):
            pending.extend(
                node.decorator_list + node.bases + [k.value for k in node.keywords]
            )
        else:
            pending.extend(ast.iter_child_nodes(node))
    return False


def is_tracking_import(
    *, module: str | None, names: tuple[str, ...], relative_level: int = 0
) -> bool:
    """Classify retained import facts; consumers never rediscover source imports."""
    return relative_level == 0 and (
        module == "apizr.tracking"
        or (module or "").startswith("apizr.tracking.")
        or (module == "apizr" and "tracking" in names)
        or (
            module is None
            and any(
                name == "apizr.tracking" or name.startswith("apizr.tracking.")
                for name in names
            )
        )
    )


class TrackingBindings(ast.NodeVisitor):
    """Require a unique earlier unconditional import and no visible mutation.

    Conditional bindings, namespace reflection and indirect writes stay uncertain.
    Function/class bodies are separate scopes; declaration expressions are retained.
    """

    def __init__(self, tree: ast.Module):
        self.tree = tree
        self.bindings: dict[str, list[ast.AST]] = defaultdict(list)
        self.uncertain = False
        # An additional bounded pass over a source AST, not a new source reader.
        for count, _ in enumerate(ast.walk(tree), 1):
            if count > 200_000:
                self.uncertain = True
                return
        self.visit(tree)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bindings[node.id].append(node)

    def visit_Attribute(self, node: ast.Attribute | ast.Subscript) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.uncertain = True
        self.generic_visit(node)

    visit_Subscript = visit_Attribute

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.bindings[alias.asname or alias.name.split(".")[0]].append(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                self.uncertain = True
            self.bindings[alias.asname or alias.name].append(node)

    def visit_FunctionDef(self, node: Function) -> None:
        self.bindings[node.name].append(node)
        for expression in (
            node.decorator_list
            + node.args.defaults
            + [value for value in node.args.kw_defaults if value is not None]
            + [
                arg.annotation
                for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                if arg.annotation is not None
            ]
            + ([node.returns] if node.returns is not None else [])
        ):
            self.visit(expression)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.bindings[node.name].append(node)
        for expression in (
            node.decorator_list + node.bases + [k.value for k in node.keywords]
        ):
            self.visit(expression)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for value in node.args.defaults + [
            d for d in node.args.kw_defaults if d is not None
        ]:
            self.visit(value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)
            self.visit(node.target)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.visit(node.iter)
        for condition in node.ifs:
            self.visit(condition)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.bindings[node.name].append(node)
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self.bindings[node.name].append(node)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self.bindings[node.name].append(node)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self.bindings[node.rest].append(node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id
            in {"globals", "locals", "vars", "exec", "eval", "__import__"}
        ) or (
            isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"
        ):
            self.uncertain = True
        self.generic_visit(node)

    def member(self, expression: ast.expr) -> str | None:
        """Resolve only exact public SDK imports, never spelling or runtime lookup."""
        if self.uncertain:
            return None
        parts: list[str] = []
        node = expression
        while isinstance(node, ast.Attribute):
            parts.insert(0, node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None
        events = self.bindings.get(node.id, [])
        if len(events) != 1:
            return None
        imported = events[0]
        if not isinstance(imported, (ast.Import, ast.ImportFrom)):
            return None
        if imported not in self.tree.body or imported.lineno >= expression.lineno:
            return None
        if isinstance(imported, ast.Import):
            for alias in imported.names:
                if (
                    alias.name == "apizr.tracking"
                    and (alias.asname or "apizr") == node.id
                ):
                    expected = (
                        parts
                        if alias.asname
                        else parts[1:]
                        if parts[:1] == ["tracking"]
                        else []
                    )
                    if len(expected) == 1 and expected[0] in SDK_MEMBERS:
                        return expected[0]
        if isinstance(imported, ast.ImportFrom) and imported.level == 0:
            for alias in imported.names:
                if (alias.asname or alias.name) != node.id:
                    continue
                if (
                    imported.module == "apizr.tracking"
                    and not parts
                    and alias.name in SDK_MEMBERS
                ):
                    return alias.name
                if (
                    imported.module == "apizr"
                    and alias.name == "tracking"
                    and len(parts) == 1
                    and parts[0] in SDK_MEMBERS
                ):
                    return parts[0]
        return None

    def inert_decorator(self, function: Function) -> bool:
        """One signature-preserving SDK decorator with literal configuration only."""
        if len(function.decorator_list) != 1 or function not in self.tree.body:
            return False
        if own_yield(function):
            return False
        expression = function.decorator_list[0]
        target = expression.func if isinstance(expression, ast.Call) else expression
        if self.member(target) != "experiment":
            return False
        if not isinstance(expression, ast.Call):
            return True
        if expression.args:
            return False
        keys = [keyword.arg for keyword in expression.keywords]
        if len(keys) != len(set(keys)) or any(
            key
            not in {
                "parameters",
                "root",
                "store",
                "source",
                "distributions",
                "max_file_bytes",
            }
            for key in keys
        ):
            return False
        for keyword in expression.keywords:
            value = keyword.value
            if keyword.arg == "parameters":
                if (
                    not isinstance(value, (ast.List, ast.Tuple))
                    or len(value.elts) > 256
                ):
                    return False
                names = [
                    e.value
                    for e in value.elts
                    if isinstance(e, ast.Constant) and type(e.value) is str
                ]
                signature = {
                    arg.arg
                    for arg in function.args.posonlyargs
                    + function.args.args
                    + function.args.kwonlyargs
                }
                if (
                    len(names) != len(value.elts)
                    or len(names) != len(set(names))
                    or any(name not in signature for name in names)
                ):
                    return False
            elif keyword.arg == "distributions":
                if (
                    not isinstance(value, (ast.List, ast.Tuple))
                    or len(value.elts) > 256
                    or any(
                        not isinstance(e, ast.Constant)
                        or type(e.value) is not str
                        or len(e.value) > 4096
                        for e in value.elts
                    )
                ):
                    return False
            elif keyword.arg == "max_file_bytes":
                if (
                    not isinstance(value, ast.Constant)
                    or type(value.value) is not int
                    or not 1 <= value.value <= 1024**4
                ):
                    return False
            elif not isinstance(value, ast.Constant) or (
                value.value is not None
                and (type(value.value) is not str or len(value.value) > 4096)
            ):
                return False
        return True
