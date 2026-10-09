"""Authoritative, bounded AST proof of stdlib class-form TypedDict shapes."""

import ast

from apizr.capabilities.model import SourceSpan
from apizr.contract_lowering import lower_node
from apizr.contract_types import ObjectField, TypeSpec

from .contracts import classify
from .model import Code, StructuredDeclaration
from .source import TYPING_NAMES, SourceFacts


def _suspected(node: ast.expr, facts: SourceFacts, names: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in names or any(
            isinstance(binding.node, ast.ImportFrom)
            and any(
                (alias.asname or alias.name) == node.id and alias.name == "TypedDict"
                for alias in binding.node.names
            )
            for binding in facts.bindings.get(node.id, ())
        )
    return isinstance(node, ast.Attribute) and node.attr == "TypedDict"


def declarations(facts: SourceFacts, module: str) -> tuple[StructuredDeclaration, ...]:
    """Retain source identity and refusals; never execute a class or annotation."""
    classes = [
        binding.node
        for bindings in facts.bindings.values()
        for binding in bindings
        if isinstance(binding.node, ast.ClassDef)
    ]
    candidates: dict[str, ast.ClassDef | ast.Assign | ast.AnnAssign] = {}
    names = {"TypedDict"}
    # Source order makes unsupported inheritance explicit, without recursive resolution.
    for node in sorted(classes, key=lambda node: node.lineno):
        if any(_suspected(base, facts, names) for base in node.bases):
            candidates.setdefault(node.name, node)
            names.add(node.name)
    for statement in facts.tree.body:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)) and isinstance(
            statement.value, ast.Call
        ):
            if _suspected(statement.value.func, facts, {"TypedDict"}):
                targets = (
                    statement.targets
                    if isinstance(statement, ast.Assign)
                    else [statement.target]
                )
                for target in targets:
                    if isinstance(target, ast.Name):
                        candidates.setdefault(target.id, statement)
    result: list[StructuredDeclaration] = []
    shapes: dict[str, TypeSpec] = {}
    for name, node in sorted(candidates.items(), key=lambda item: item[1].lineno):
        source = SourceSpan(
            module=module,
            symbol=name,
            line=node.lineno,
            end_line=node.end_lineno or node.lineno,
        )
        try:
            shape = _shape(name, node, facts, shapes, set(candidates))
        except ValueError as error:
            result.append(
                StructuredDeclaration(name=name, source=source, problem=str(error))
            )
        else:
            shapes[name] = shape
            result.append(StructuredDeclaration(name=name, source=source, type=shape))
    return tuple(result)


def _shape(
    name: str,
    node: ast.stmt,
    facts: SourceFacts,
    shapes: dict[str, TypeSpec],
    candidates: set[str],
) -> TypeSpec:
    if not isinstance(node, ast.ClassDef):
        raise ValueError(
            "Functional TypedDict declarations are unsupported; use class form"
        )
    if getattr(node, "type_params", ()):
        raise ValueError("Generic TypedDict type parameters are unsupported")
    if (
        node not in facts.tree.body
        or len(facts.bindings[name]) != 1
        or name in facts.mutated_roots
    ):
        raise ValueError(
            "TypedDict must have one unconditional, unmodified module binding"
        )
    if (
        len(node.bases) != 1
        or facts.typing_marker(node.bases[0], {"TypedDict"}) != "TypedDict"
    ):
        raise ValueError(
            "TypedDict requires a proven stdlib base; inheritance and ambiguous bases are unsupported"
        )
    if node.decorator_list:
        raise ValueError("TypedDict decorators are unsupported")
    total = True
    if node.keywords:
        if len(node.keywords) != 1 or node.keywords[0].arg != "total":
            raise ValueError(
                "Only literal total=True/False is supported; metaclass and other keywords are unsupported"
            )
        value = node.keywords[0].value
        if not isinstance(value, ast.Constant) or type(value.value) is not bool:
            raise ValueError("TypedDict total must be a literal boolean")
        total = value.value
    fields: list[ObjectField] = []
    for index, statement in enumerate(node.body):
        if isinstance(statement, ast.Pass):
            continue
        if (
            index == 0
            and isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        if (
            not isinstance(statement, ast.AnnAssign)
            or not isinstance(statement.target, ast.Name)
            or statement.value is not None
        ):
            raise ValueError(
                "TypedDict body supports only a docstring, annotated fields and pass"
            )
        annotation = statement.annotation
        required = total
        if isinstance(annotation, ast.Subscript):
            marker = facts.typing_marker(annotation.value, {"Required", "NotRequired"})
            if marker is not None:
                required = marker == "Required"
                annotation = annotation.slice
        for child in ast.walk(annotation):
            if isinstance(child, ast.Call):
                raise ValueError("Annotation calls are unsupported in TypedDict fields")
            if (
                isinstance(child, ast.Name)
                and child.id in candidates
                and child.id not in shapes
            ):
                raise ValueError(
                    "Forward, recursive or unsupported TypedDict field reference: "
                    + child.id
                )
            if (
                isinstance(child, (ast.Name, ast.Attribute))
                and facts.typing_name(child) in TYPING_NAMES
            ):
                if facts.typing_marker(child, TYPING_NAMES) is None:
                    raise ValueError(
                        "TypedDict field typing names require an earlier unambiguous stdlib import"
                    )
        codes = classify(annotation, facts, shapes)
        if any(code != Code.UNCONSTRAINED for code in codes):
            raise ValueError(
                "Unsupported, forward or ambiguous TypedDict field type: "
                + ast.unparse(annotation)
            )
        fields.append(
            ObjectField(
                name=_field_name(node.name, statement.target.id),
                required=required,
                type=lower_node(annotation, shapes),
            )
        )
    pending = [(field.type, 1) for field in fields]
    count = 0
    while pending:
        spec, depth = pending.pop()
        count += 1
        if depth > 32 or count > 4096:
            raise ValueError(
                "TypedDict shape exceeds the bounded 32-level/4096-node contract"
            )
        pending.extend((item, depth + 1) for item in spec.items)
        pending.extend((field.type, depth + 1) for field in spec.fields)
    return TypeSpec(kind="object", fields=tuple(fields))


def _field_name(class_name: str, declared: str) -> str:
    """Freeze Python class private-name mangling without reading annotations."""
    owner = class_name.lstrip("_")
    if owner and declared.startswith("__") and not declared.endswith("__"):
        return "_" + owner + declared
    return declared
