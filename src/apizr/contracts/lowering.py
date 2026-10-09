"""Lower retained annotation expressions; never inspect original project source."""

import ast
import math
from collections.abc import Mapping

from apizr.capabilities.types import DeclaredType
from apizr.contract_types import Scalar, TypeSpec


class ContractError(ValueError):
    """Readiness approved an input the contract boundary cannot represent."""


def literal(node: ast.expr) -> Scalar:
    if isinstance(node, ast.Constant):
        value = node.value
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float) and math.isfinite(value):
            return value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = literal(node.operand)
        if type(value) in (int, float) and isinstance(value, (int, float)):
            return -value if isinstance(node.op, ast.USub) else value
    raise ContractError("Non-scalar Literal in an approved contract")


def lower(
    annotation: DeclaredType | None, structured: Mapping[str, TypeSpec] | None = None
) -> TypeSpec:
    if annotation is None:
        return TypeSpec(kind="any")
    return lower_node(ast.parse(annotation.declared, mode="eval").body, structured)


def lower_node(
    node: ast.expr, structured: Mapping[str, TypeSpec] | None = None
) -> TypeSpec:
    if isinstance(node, ast.Name) and structured and node.id in structured:
        return structured[node.id]
    if isinstance(node, ast.Constant) and node.value is None:
        return TypeSpec(kind="null")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return TypeSpec(
            kind="union",
            items=(
                lower_node(node.left, structured),
                lower_node(node.right, structured),
            ),
        )
    base = node.value if isinstance(node, ast.Subscript) else node
    name = (
        base.id
        if isinstance(base, ast.Name)
        else base.attr
        if isinstance(base, ast.Attribute)
        else ""
    )
    names = {"List": "list", "Dict": "dict", "Tuple": "tuple", "Set": "set"}
    name = names.get(name, name)
    if not isinstance(node, ast.Subscript):
        if name in {"int", "str", "float", "bool"}:
            return TypeSpec.model_validate({"kind": name})
        if name == "Any":
            return TypeSpec(kind="any")
        if name in {"list", "dict", "tuple", "set"}:
            return TypeSpec.model_validate(
                {"kind": name, "items": [{"kind": "any"}], "variadic": name == "tuple"}
            )
        raise ContractError(
            f"Approved input type is not self-contained: {ast.unparse(node)}"
        )
    members = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
    if name == "Literal":
        return TypeSpec(kind="literal", values=tuple(literal(m) for m in members))
    if name in {"Optional", "Union"}:
        items = tuple(lower_node(m, structured) for m in members)
        if name == "Optional":
            items += (TypeSpec(kind="null"),)
        return TypeSpec(kind="union", items=items)
    if name == "dict" and len(members) == 2:
        if lower_node(members[0], structured).kind != "str":
            raise ContractError("JSON object keys require str")
        return TypeSpec(kind="dict", items=(lower_node(members[1], structured),))
    if name in {"list", "set"} and len(members) == 1:
        return TypeSpec.model_validate(
            {"kind": name, "items": [lower_node(members[0], structured)]}
        )
    if name == "tuple":
        variadic = (
            len(members) == 2
            and isinstance(members[1], ast.Constant)
            and members[1].value is Ellipsis
        )
        return TypeSpec(
            kind="tuple",
            items=tuple(
                lower_node(m, structured)
                for m in (members[:1] if variadic else members)
            ),
            variadic=variadic,
        )
    raise ContractError(f"Unsupported syntax in approved input: {ast.unparse(node)}")
