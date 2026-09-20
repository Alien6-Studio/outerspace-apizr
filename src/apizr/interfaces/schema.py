"""Lower self-contained IR type syntax, never the original source contract."""

import ast
import math

from pydantic import JsonValue

from apizr.capabilities.types import DeclaredType

from .model import InvocationContract, Scalar, TypeSpec


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


def lower(annotation: DeclaredType | None) -> TypeSpec:
    if annotation is None:
        return TypeSpec(kind="any")
    return lower_node(ast.parse(annotation.declared, mode="eval").body)


def lower_node(node: ast.expr) -> TypeSpec:
    if isinstance(node, ast.Constant) and node.value is None:
        return TypeSpec(kind="null")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return TypeSpec(
            kind="union", items=(lower_node(node.left), lower_node(node.right))
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
        items = tuple(lower_node(m) for m in members)
        if name == "Optional":
            items += (TypeSpec(kind="null"),)
        return TypeSpec(kind="union", items=items)
    if name == "dict" and len(members) == 2:
        if lower_node(members[0]).kind != "str":
            raise ContractError("JSON object keys require str")
        return TypeSpec(kind="dict", items=(lower_node(members[1]),))
    if name in {"list", "set"} and len(members) == 1:
        return TypeSpec.model_validate(
            {"kind": name, "items": [lower_node(members[0])]}
        )
    if name == "tuple":
        variadic = (
            len(members) == 2
            and isinstance(members[1], ast.Constant)
            and members[1].value is Ellipsis
        )
        return TypeSpec(
            kind="tuple",
            items=tuple(lower_node(m) for m in (members[:1] if variadic else members)),
            variadic=variadic,
        )
    raise ContractError(f"Unsupported syntax in approved input: {ast.unparse(node)}")


def json_schema(spec: TypeSpec) -> dict[str, JsonValue]:
    primitive = {
        "int": "integer",
        "float": "number",
        "str": "string",
        "bool": "boolean",
        "null": "null",
    }
    if spec.kind == "any":
        return {}
    if spec.kind in primitive:
        return {"type": primitive[spec.kind]}
    if spec.kind == "literal":
        choices: list[JsonValue] = []
        for value in spec.values:
            scalar_type = (
                "null"
                if value is None
                else "boolean"
                if isinstance(value, bool)
                else "string"
                if isinstance(value, str)
                else "integer"
                if isinstance(value, int)
                else "number"
            )
            choices.append({"type": scalar_type, "const": value})
        return (
            choices[0]
            if len(choices) == 1 and isinstance(choices[0], dict)
            else {"anyOf": choices}
        )
    if spec.kind == "union":
        members: list[JsonValue] = [json_schema(item) for item in spec.items]
        return {"anyOf": members}
    if spec.kind == "dict":
        return {"type": "object", "additionalProperties": json_schema(spec.items[0])}
    if spec.kind == "tuple" and not spec.variadic:
        prefix: list[JsonValue] = [json_schema(item) for item in spec.items]
        return {
            "type": "array",
            "prefixItems": prefix,
            "minItems": len(prefix),
            "maxItems": len(prefix),
        }
    result: dict[str, JsonValue] = {
        "type": "array",
        "items": json_schema(spec.items[0]),
    }
    if spec.kind == "set":
        result["uniqueItems"] = True
    return result


def request_schema(endpoint: InvocationContract) -> dict[str, JsonValue]:
    properties: dict[str, JsonValue] = {
        p.name: json_schema(p.type) for p in endpoint.parameters
    }
    required: list[JsonValue] = [p.name for p in endpoint.parameters if p.required]
    schema: dict[str, JsonValue] = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    positional = [p for p in endpoint.parameters if p.kind == "positional_only"]
    dependencies: dict[str, JsonValue] = {}
    for index, parameter in enumerate(positional):
        preceding: list[JsonValue] = [
            p.name for p in positional[:index] if not p.required
        ]
        if preceding:
            dependencies[parameter.name] = preceding
    if dependencies:
        schema["dependentRequired"] = dependencies
    return schema
