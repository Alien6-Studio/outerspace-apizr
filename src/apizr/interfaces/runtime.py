"""Standalone trusted-code runtime: integrity, binding and JSON invocation."""

import importlib.machinery
import importlib.util
import inspect
import math
import sys
import types
from hashlib import sha256
from pathlib import Path
from typing import Literal, TypeAlias, TypedDict

JSON: TypeAlias = None | bool | int | float | str | list["JSON"] | dict[str, "JSON"]


class RuntimeType(TypedDict):
    kind: str
    items: list["RuntimeType"]
    values: list[str | int | float | bool | None]
    variadic: bool


class RuntimeParameter(TypedDict):
    name: str
    kind: str
    required: bool
    type: RuntimeType


class RuntimeInvocation(TypedDict):
    name: str
    capability_id: str
    execution: Literal["sync", "async"]
    parameters: list[RuntimeParameter]


class RuntimeDigest(TypedDict):
    value: str


class RuntimeSource(TypedDict):
    module: str


class SourcePlan(TypedDict):
    executable_path: str
    executable_digest: RuntimeDigest
    source: RuntimeSource


class IntegrityError(RuntimeError):
    pass


class BindingError(RuntimeError):
    pass


def load_source(root: Path, plan: SourcePlan) -> types.ModuleType:
    path = root / plan["executable_path"]
    content = path.read_bytes()
    if sha256(content).hexdigest() != plan["executable_digest"]["value"]:
        raise IntegrityError("Bundled source digest mismatch; refusing runtime import")
    module_name = plan["source"]["module"]
    pieces = module_name.split(".")
    created: list[str] = []
    try:
        for index in range(1, len(pieces)):
            name = ".".join(pieces[:index])
            if name in sys.modules:
                raise BindingError(
                    "Logical source package conflicts with a loaded module"
                )
            package = types.ModuleType(name)
            package.__path__ = [str(root / "source" / Path(*pieces[:index]))]
            package.__package__ = name
            sys.modules[name] = package
            created.append(name)
        if module_name in sys.modules:
            raise BindingError("Logical source module is already loaded")

        class VerifiedLoader(importlib.machinery.SourceFileLoader):
            def get_code(self, fullname: str) -> types.CodeType:
                # Compile the verified bytes, never a cached .pyc or a second read.
                return compile(content, str(path), "exec", dont_inherit=True)

        spec = importlib.util.spec_from_file_location(
            module_name, path, loader=VerifiedLoader(module_name, str(path))
        )
        if spec is None or spec.loader is None:
            raise BindingError("Could not construct the bundled source loader")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        created.append(module_name)
        spec.loader.exec_module(module)
        return module
    except BaseException:
        for name in reversed(created):
            sys.modules.pop(name, None)
        raise


def verify_binding(
    module: types.ModuleType, endpoint: RuntimeInvocation
) -> types.FunctionType:
    function = getattr(module, endpoint["name"], None)
    if not callable(function) or not inspect.isfunction(function):
        raise BindingError("Expected a Python function for " + endpoint["name"])
    if inspect.isgeneratorfunction(function) or inspect.isasyncgenfunction(function):
        raise BindingError("Unexpected generator binding for " + endpoint["name"])
    if inspect.iscoroutinefunction(function) != (endpoint["execution"] == "async"):
        raise BindingError("Execution form mismatch for " + endpoint["name"])
    # Do not read __annotations__ or evaluate deferred/string annotations.
    code = function.__code__
    if code.co_flags & (inspect.CO_VARARGS | inspect.CO_VARKEYWORDS):
        raise BindingError("Unexpected variadic binding for " + endpoint["name"])
    positional = code.co_argcount
    defaults = function.__defaults__ or ()
    kwdefaults = function.__kwdefaults__ or {}
    actual: list[tuple[str, str, bool]] = []
    for index, name in enumerate(
        code.co_varnames[: positional + code.co_kwonlyargcount]
    ):
        kind = (
            "positional_only"
            if index < code.co_posonlyargcount
            else "positional_or_keyword"
            if index < positional
            else "keyword_only"
        )
        required = (
            index < positional - len(defaults)
            if index < positional
            else name not in kwdefaults
        )
        actual.append((name, kind, required))
    expected = [(p["name"], p["kind"], p["required"]) for p in endpoint["parameters"]]
    if actual != expected:
        raise BindingError("Parameter binding mismatch for " + endpoint["name"])
    return function


def json_value(value: JSON) -> JSON:
    if value is None or type(value) in (str, bool, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    raise ValueError("Expected a finite JSON value")


def validate(value: JSON, spec: RuntimeType) -> object:
    kind = spec["kind"]
    items = spec["items"]
    if kind == "any":
        return json_value(value)
    if kind == "null" and value is None:
        return None
    if kind == "str" and isinstance(value, str):
        return value
    if kind == "bool" and type(value) is bool:
        return value
    if kind == "int" and type(value) is int:
        return value
    if (
        kind == "int"
        and type(value) is float
        and math.isfinite(value)
        and value.is_integer()
    ):
        return int(value)
    if (
        kind == "float"
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        try:
            number = float(value)
            if math.isfinite(number):
                return number
        except OverflowError:
            pass
    if kind == "literal":
        for choice in spec["values"]:
            if (
                type(choice) in (int, float)
                and type(value) in (int, float)
                and value == choice
            ):
                return choice
            if type(choice) is type(value) and choice == value:
                return choice
    if kind == "union":
        for member in items:
            try:
                return validate(value, member)
            except ValueError:
                pass
    if kind == "dict" and isinstance(value, dict):
        return {key: validate(item, items[0]) for key, item in value.items()}
    if kind in ("list", "tuple", "set") and isinstance(value, list):
        if kind == "tuple" and not spec["variadic"]:
            if len(value) != len(items):
                raise ValueError("Tuple length mismatch")
            return tuple(
                validate(item, member)
                for item, member in zip(value, items, strict=True)
            )
        converted = [validate(item, items[0]) for item in value]
        if kind == "tuple":
            return tuple(converted)
        if kind == "set":
            try:
                result = set(converted)
            except TypeError as error:
                raise ValueError("Set members must be hashable") from error
            if len(result) != len(converted):
                raise ValueError("Set members must be unique")
            return result
        return converted
    raise ValueError("Value does not match the declared input type")


def arguments(
    function: types.FunctionType, endpoint: RuntimeInvocation, payload: JSON
) -> tuple[list[object], dict[str, object]]:
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    parameters = endpoint["parameters"]
    if set(payload) - {p["name"] for p in parameters}:
        raise ValueError("Unexpected request field")
    values: dict[str, object] = {}
    for parameter in parameters:
        name = parameter["name"]
        if name not in payload:
            if parameter["required"]:
                raise ValueError("Missing required field: " + name)
        else:
            values[name] = validate(payload[name], parameter["type"])
    positional = [p for p in parameters if p["kind"] == "positional_only"]
    supplied = [index for index, p in enumerate(positional) if p["name"] in values]
    last = max(supplied, default=-1)
    args: list[object] = []
    for parameter in positional[: last + 1]:
        name = parameter["name"]
        if name not in values:
            # Python cannot encode a positional gap without injecting a default.
            raise ValueError("Supply preceding positional-only field: " + name)
        args.append(values.pop(name))
    return args, values
