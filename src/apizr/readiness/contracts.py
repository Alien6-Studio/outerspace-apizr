"""Syntactic JSON input suitability, without runtime type/alias resolution."""

import ast
import math

from .model import Code
from .source import SourceFacts


def classify(node: ast.expr | None, facts: SourceFacts) -> tuple[Code, ...]:
    if node is None:
        return (Code.UNCONSTRAINED,)
    if isinstance(node, ast.Constant):
        return () if node.value is None else (Code.UNRESOLVED_TYPE,)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return classify(node.left, facts) + classify(node.right, facts)
    base = node.value if isinstance(node, ast.Subscript) else node
    name = facts.typing_name(base)
    if name in {"Callable", "bytes"}:
        return (Code.NON_JSON,)
    if not isinstance(node, ast.Subscript):
        if name in {"str", "int", "float", "bool"}:
            return ()
        if name in {
            "Any",
            "list",
            "dict",
            "tuple",
            "set",
            "List",
            "Dict",
            "Tuple",
            "Set",
        }:
            return (Code.UNCONSTRAINED,)
        return (Code.UNRESOLVED_TYPE,)
    members = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
    if name == "Literal":
        if members and all(json_literal(m) for m in members):
            return ()
        return (Code.NON_JSON,)
    if name == "Annotated" and len(members) >= 2:
        return classify(members[0], facts) + (Code.METADATA,)
    if name in {"Union", "Optional"}:
        if not members or (name == "Optional" and len(members) != 1):
            return (Code.UNRESOLVED_TYPE,)
    elif name in {"list", "List", "set", "Set"}:
        if len(members) != 1:
            return (Code.UNRESOLVED_TYPE,)
    elif name in {"dict", "Dict"}:
        if len(members) != 2:
            return (Code.UNRESOLVED_TYPE,)
        if facts.typing_name(members[0]) != "str":
            return (Code.NON_JSON,)
    elif name in {"tuple", "Tuple"}:
        if (
            len(members) == 2
            and isinstance(members[-1], ast.Constant)
            and members[-1].value is Ellipsis
        ):
            members = members[:1]
    else:
        return (Code.UNRESOLVED_TYPE,)
    return tuple(code for member in members for code in classify(member, facts))


def json_literal(node: ast.expr) -> bool:
    """Accept scalar JSON literals, including signed finite numbers, without eval."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return (
            isinstance(node.operand, ast.Constant)
            and type(node.operand.value) in {int, float}
            and (
                not isinstance(node.operand.value, float)
                or math.isfinite(node.operand.value)
            )
        )
    return isinstance(node, ast.Constant) and (
        node.value is None
        or isinstance(node.value, (str, bool, int))
        or (isinstance(node.value, float) and math.isfinite(node.value))
    )
