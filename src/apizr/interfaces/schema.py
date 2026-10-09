"""Lower self-contained IR type syntax, never the original source contract."""

from pydantic import JsonValue

from apizr.contract_lowering import ContractError as ContractError
from apizr.contract_lowering import literal as literal
from apizr.contract_lowering import lower as lower
from apizr.contract_lowering import lower_node as lower_node

from .model import InvocationContract, TypeSpec


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
    if spec.kind == "object":
        return {
            "type": "object",
            "properties": {
                field.name: json_schema(field.type) for field in spec.fields
            },
            "required": [field.name for field in spec.fields if field.required],
            "additionalProperties": False,
        }
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
