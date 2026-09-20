"""Static AST inspection. Never import, resolve or execute the analyzed program."""

import ast
import io
import tokenize
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .model import (
    Availability,
    Capability,
    CapabilityDocument,
    Diagnostic,
    DiagnosticCode,
    Digest,
    ExecutionForm,
    Overload,
    Parameter,
    ParameterKind,
    Returns,
    Severity,
    Signature,
    Source,
    SourceSpan,
)
from .types import (
    DeclaredType,
    Evidence,
    Expression,
    TypeForm,
    declared_type,
    logical_module,
)

Function = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class _Definition:
    node: Function
    index: int | None


class _ModuleScope(ast.NodeVisitor):
    """Walk module control flow, but never enter a function/class/lambda scope."""

    def __init__(self, tree: ast.Module) -> None:
        self.definitions: list[_Definition] = []
        self.bindings: dict[str, list[ast.AST]] = defaultdict(list)
        self.imports: dict[str, list[ast.Import | ast.ImportFrom]] = defaultdict(list)
        self.lambdas: list[tuple[str, ast.Assign | ast.AnnAssign]] = []
        self.indices = {id(node): index for index, node in enumerate(tree.body)}
        self.visit(tree)

    def visit_FunctionDef(self, node: Function) -> None:
        self.bindings[node.name].append(node)
        self.definitions.append(_Definition(node, self.indices.get(id(node))))
        # Definition-time expressions can also bind names (e.g. walrus defaults).
        for expression in (*node.decorator_list, *node.args.defaults):
            self.visit(expression)
        for expression in node.args.kw_defaults:
            if expression is not None:
                self.visit(expression)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.bindings[node.name].append(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bindings[node.id].append(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            self.bindings[local].append(node)
            if alias.name == "typing":
                self.imports[local].append(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            local = alias.asname or alias.name
            self.bindings[local].append(node)
            if node.level == 0 and node.module == "typing" and alias.name == "overload":
                self.imports[local].append(node)

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

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Lambda):
            self.lambdas.extend(
                (t.id, node) for t in node.targets if isinstance(t, ast.Name)
            )
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.value, ast.Lambda) and isinstance(node.target, ast.Name):
            self.lambdas.append((node.target.id, node))
        self.generic_visit(node)

    def overload_marker(self, expression: ast.expr, function: Function) -> bool | None:
        """True = evidenced marker, None = suspected/ambiguous, False = other."""
        root: str
        module_import: bool
        if isinstance(expression, ast.Name):
            root, module_import = expression.id, False
            candidates = self.imports.get(root, [])
            if root != "overload" and not any(
                isinstance(n, ast.ImportFrom) for n in candidates
            ):
                return False
        elif isinstance(expression, ast.Attribute) and expression.attr == "overload":
            if not isinstance(expression.value, ast.Name):
                return None
            root, module_import = expression.value.id, True
        else:
            return False
        imports = self.imports.get(root, [])
        if len(imports) != 1 or len(self.bindings[root]) != 1:
            return None
        imported = imports[0]
        if (
            id(imported) not in self.indices
            or imported.lineno >= function.lineno
            or module_import != isinstance(imported, ast.Import)
        ):
            return None
        return True


class _OwnYield(ast.NodeVisitor):
    found = False

    def visit_Yield(self, node: ast.Yield | ast.YieldFrom) -> None:
        self.found = True

    visit_YieldFrom = visit_Yield

    def visit_FunctionDef(self, node: Function | ast.ClassDef | ast.Lambda) -> None:
        pass

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef
    visit_Lambda = visit_FunctionDef


def _execution(node: Function) -> ExecutionForm:
    visitor = _OwnYield()
    for statement in node.body:
        visitor.visit(statement)
    if isinstance(node, ast.AsyncFunctionDef):
        return ExecutionForm.ASYNC_GENERATOR if visitor.found else ExecutionForm.ASYNC
    return ExecutionForm.GENERATOR if visitor.found else ExecutionForm.SYNC


class _Analyzer:
    def __init__(self, tree: ast.Module, source: Source) -> None:
        self.source = source
        self.scope = _ModuleScope(tree)
        self.diagnostics: list[Diagnostic] = []

    def span(self, node: ast.stmt, symbol: str) -> SourceSpan:
        return SourceSpan(
            module=self.source.module,
            symbol=symbol,
            line=node.lineno,
            end_line=node.end_lineno or node.lineno,
        )

    def diagnostic(
        self,
        code: DiagnosticCode,
        severity: Severity,
        message: str,
        node: ast.stmt,
        symbol: str,
    ) -> None:
        self.diagnostics.append(
            Diagnostic(
                code=code,
                severity=severity,
                message=message,
                source=self.span(node, symbol),
            )
        )

    def annotation(
        self, node: ast.expr | None, function: Function
    ) -> DeclaredType | None:
        if node is None:
            return None
        result = declared_type(node)
        if result.form == TypeForm.UNKNOWN:
            self.diagnostic(
                DiagnosticCode.TYPE_STRUCTURE,
                Severity.INFO,
                "Type structure is unknown; the complete declaration is retained.",
                function,
                function.name,
            )
        return result

    def signature(self, node: Function) -> Signature | None:
        args = node.args
        if args.vararg is not None or args.kwarg is not None:
            self.diagnostic(
                DiagnosticCode.VARIADIC,
                Severity.ERROR,
                "Variadic signatures are not executable v1 contracts.",
                node,
                node.name,
            )
            return None
        positional = args.posonlyargs + args.args
        defaults: list[ast.expr | None] = [None] * (
            len(positional) - len(args.defaults)
        ) + list(args.defaults)
        parameters: list[Parameter] = []
        for index, (arg, default) in enumerate(
            zip(positional + args.kwonlyargs, defaults + args.kw_defaults, strict=True)
        ):
            kind = ParameterKind.KEYWORD_ONLY
            if index < len(args.posonlyargs):
                kind = ParameterKind.POSITIONAL_ONLY
            elif index < len(positional):
                kind = ParameterKind.POSITIONAL_OR_KEYWORD
            parameters.append(
                Parameter(
                    name=arg.arg,
                    kind=kind,
                    required=default is None,
                    annotation=self.annotation(arg.annotation, node),
                    default=Expression(declared=ast.unparse(default))
                    if default is not None
                    else None,
                )
            )
        return Signature(
            parameters=tuple(parameters),
            returns=Returns(annotation=self.annotation(node.returns, node)),
        )

    def capability(self, definitions: list[_Definition]) -> Capability | None:
        stubs: list[_Definition] = []
        concrete: list[_Definition] = []
        ambiguous = False
        for definition in definitions:
            markers = [
                self.scope.overload_marker(d, definition.node)
                for d in definition.node.decorator_list
            ]
            if any(m is None for m in markers):
                ambiguous = True
            if True in markers or None in markers:
                stubs.append(definition)
                ambiguous |= len(markers) != 1
            else:
                concrete.append(definition)
        first = definitions[0].node
        if len(concrete) > 1:
            self.diagnostic(
                DiagnosticCode.DUPLICATE,
                Severity.ERROR,
                "Multiple concrete definitions have the same logical symbol; none was selected.",
                first,
                first.name,
            )
            return None
        if stubs:
            indices = [d.index for d in definitions]
            start = indices[0]
            ambiguous |= (
                len(concrete) != 1
                or concrete[-1] != definitions[-1]
                or start is None
                or indices != list(range(start or 0, (start or 0) + len(indices)))
                or any(
                    isinstance(d.node, ast.AsyncFunctionDef)
                    != isinstance(first, ast.AsyncFunctionDef)
                    for d in definitions
                )
            )
            if ambiguous:
                self.diagnostic(
                    DiagnosticCode.OVERLOAD,
                    Severity.ERROR,
                    "Overload declarations cannot be associated unambiguously with one implementation.",
                    first,
                    first.name,
                )
                return None
        node = concrete[0].node
        signature = self.signature(node)
        overloads: list[Overload] = []
        for stub in stubs:
            contract = self.signature(stub.node)
            if contract is None:
                signature = None
            else:
                overloads.append(
                    Overload(source=self.span(stub.node, node.name), signature=contract)
                )
        if signature is None:
            return None
        conditional = concrete[0].index is None
        if conditional:
            self.diagnostic(
                DiagnosticCode.CONDITIONAL,
                Severity.WARNING,
                "Definition is under module control flow; runtime availability is unknown.",
                node,
                node.name,
            )
        if node.decorator_list:
            self.diagnostic(
                DiagnosticCode.BINDING,
                Severity.WARNING,
                "Decorators may replace the function binding; their semantics are unknown.",
                node,
                node.name,
            )
        unknown = conditional or bool(node.decorator_list)
        return Capability(
            id=f"python:{self.source.module}:{node.name}",
            name=node.name,
            qualified_name=node.name,
            source=self.span(node, node.name),
            docstring=ast.get_docstring(node),
            execution=_execution(node),
            signature=signature,
            decorators=tuple(
                Expression(declared=ast.unparse(d)) for d in node.decorator_list
            ),
            overloads=tuple(overloads),
            availability=Availability(
                value="unknown" if unknown else "unconditional",
                evidence=Evidence.UNKNOWN if unknown else Evidence.OBSERVED,
            ),
        )

    def document(self) -> CapabilityDocument:
        groups: dict[str, list[_Definition]] = defaultdict(list)
        for definition in self.scope.definitions:
            groups[definition.node.name].append(definition)
        capabilities: list[Capability] = []
        for definitions in groups.values():
            capability = self.capability(definitions)
            if capability is not None:
                capabilities.append(capability)
        for name, node in self.scope.lambdas:
            self.diagnostic(
                DiagnosticCode.BINDING,
                Severity.WARNING,
                "Lambda assignments are not module-level function-definition contracts.",
                node,
                name,
            )
        return CapabilityDocument(
            source=self.source,
            capabilities=tuple(capabilities),
            diagnostics=tuple(self.diagnostics),
        )


def inspect_source(source: str | bytes, *, module_name: str) -> CapabilityDocument:
    """Inspect source text/bytes without execution. Strings mean UTF-8 bytes."""
    module = logical_module(module_name)
    raw = source.encode("utf-8") if isinstance(source, str) else source
    if isinstance(source, str):
        text = source
    else:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        text = raw.decode(encoding)
    tree = ast.parse(text, filename="<capability-source>")
    return _Analyzer(
        tree, Source(kind="python", module=module, digest=Digest.of_bytes(raw))
    ).document()


def inspect_file(path: str | Path, *, module_name: str) -> CapabilityDocument:
    """Read exactly the explicitly supplied file, without resolving imports."""
    return inspect_source(Path(path).read_bytes(), module_name=module_name)
