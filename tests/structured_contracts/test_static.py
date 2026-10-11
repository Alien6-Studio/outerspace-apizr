import ast
import json

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from apizr.capabilities import canonical_bytes as ir_bytes
from apizr.capabilities.types import declared_type
from apizr.contract_lowering import ContractError, lower
from apizr.contract_types import ObjectField, TypeSpec
from apizr.generators.mcp.generator import render as mcp
from apizr.generators.rest.generator import render as rest
from apizr.inspection import Inspection, inspect_source
from apizr.interfaces.planner import GenerationRefused, plan
from apizr.interfaces.schema import json_schema
from apizr.readiness import canonical_bytes as readiness_bytes
from apizr.readiness.model import Code, ReadinessReport, StructuredDeclaration
from apizr.readiness.source import SourceFacts
from apizr.readiness.structured import declarations

MINIMAL = """from typing import TypedDict
class Input(TypedDict):
    value: int
def calculate(payload: Input) -> int:
    return payload["value"] * 2
"""
MINIMAL_SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "integer"}},
    "required": ["value"],
    "additionalProperties": False,
}


@pytest.mark.parametrize(
    "annotation,message",
    [
        ("Literal[1e999]", "Non-scalar"),
        ("Literal[-True]", "Non-scalar"),
        ("dict[int, str]", "keys require str"),
        ("list[int, str]", "Unsupported syntax"),
    ],
)
def test_shared_lowering_rejects_invalid_declared_contracts(annotation, message):
    # The public contract boundary must refuse malformed retained annotations
    # independently of the readiness assessment that normally precedes it.
    with pytest.raises(ContractError, match=message):
        lower(declared_type(ast.parse(annotation, mode="eval").body))


NESTED = """from typing import TypedDict, Required, NotRequired
class Features(TypedDict):
    age: int
    score: float
class PredictionInput(TypedDict, total=False):
    customer_id: Required[str]
    features: Required[Features]
    note: NotRequired[str]
def predict(payload: PredictionInput) -> float:
    return payload["features"]["age"] * payload["features"]["score"]
"""


def inspect(source=MINIMAL):
    return inspect_source(source, module_name="typed_sample")


@pytest.mark.parametrize(
    "imports,base",
    [
        ("from typing import TypedDict", "TypedDict"),
        ("import typing", "typing.TypedDict"),
        ("import typing as t", "t.TypedDict"),
        ("from typing import TypedDict as TD", "TD"),
    ],
)
def test_proven_stdlib_forms(imports, base):
    source = MINIMAL.replace("from typing import TypedDict", imports).replace(
        "class Input(TypedDict)", f"class Input({base})"
    )
    inspected = inspect(source)
    assert inspected.readiness.assessments[0].can_generate_interface
    evidence = inspected.readiness.structured_types[0]
    assert evidence.name == evidence.source.symbol == "Input"
    assert evidence.source.module == "typed_sample" and evidence.source.line == 2
    assert evidence.problem is None and json_schema(evidence.type) == MINIMAL_SCHEMA
    assert (
        inspected.capability_ir.capabilities[0].signature.returns.enforcement == "none"
    )
    assert Inspection.model_validate_json(inspected.model_dump_json()) == inspected
    contract = plan(inspected, source.encode()).capabilities[0]
    assert json_schema(contract.parameters[0].type) == MINIMAL_SCHEMA
    assert "structured_types" not in inspected.capability_ir.model_dump()


@pytest.mark.parametrize(
    "total,annotation,required",
    [
        ("", "int", True),
        (", total=True", "int", True),
        (", total=False", "int", False),
        (", total=False", "Required[int]", True),
        ("", "NotRequired[int]", False),
        (", total=False", "NotRequired[int]", False),
        ("", "Required[int]", True),
    ],
)
def test_requiredness(total, annotation, required):
    source = (
        MINIMAL.replace("import TypedDict", "import TypedDict, Required, NotRequired")
        .replace("(TypedDict)", f"(TypedDict{total})")
        .replace("value: int", "value: " + annotation)
    )
    schema = json_schema(inspect(source).readiness.structured_types[0].type)
    assert schema["required"] == (["value"] if required else [])
    assert schema["properties"] == MINIMAL_SCHEMA["properties"]


@pytest.mark.parametrize(
    "import_line,required,optional",
    [
        ("import typing as t", "t.Required", "t.NotRequired"),
        ("from typing import TypedDict, Required as R, NotRequired as N", "R", "N"),
    ],
)
def test_requiredness_qualified_and_aliases(import_line, required, optional):
    source = (
        NESTED.replace(
            "from typing import TypedDict, Required, NotRequired", import_line
        )
        .replace("Required[str]", required + "[str]")
        .replace("Required[Features]", required + "[Features]")
        .replace("Not" + required + "[str]", optional + "[str]")
    )
    if import_line.startswith("import"):
        source = source.replace("(TypedDict", "(t.TypedDict")
    inspected = inspect(source)
    assert inspected.readiness.assessments[0].can_generate_interface
    assert {
        f.name: f.required for f in inspected.readiness.structured_types[1].type.fields
    } == {"customer_id": True, "features": True, "note": False}


@pytest.mark.parametrize(
    "body,expected",
    [
        ('    """Shape only."""\n    pass', {}),
        ("    pass\n    value: int\n    pass", MINIMAL_SCHEMA["properties"]),
        (
            "    value: list[int | None]",
            {
                "value": {
                    "type": "array",
                    "items": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                }
            },
        ),
        (
            '    value: Literal["ok", -1]',
            {
                "value": {
                    "anyOf": [
                        {"type": "string", "const": "ok"},
                        {"type": "integer", "const": -1},
                    ]
                }
            },
        ),
        ("    value: Any", {"value": {}}),
        (
            "    value: dict[str, tuple[int, ...]]",
            {
                "value": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                }
            },
        ),
    ],
)
def test_shared_field_vocabulary_and_empty_object(body, expected):
    source = MINIMAL.replace(
        "import TypedDict", "import TypedDict, Literal, Any"
    ).replace("    value: int", body)
    inspected = inspect(source)
    assert inspected.readiness.assessments[0].can_generate_interface
    assert (
        json_schema(inspected.readiness.structured_types[0].type)["properties"]
        == expected
    )


@pytest.mark.parametrize(
    "source,problem",
    [
        (
            MINIMAL.replace("    value: int", "    value: int\n    value: str"),
            "Duplicate",
        ),
        (MINIMAL.replace("    value: int", "    value: int = 2"), "body"),
        (MINIMAL.replace("    value: int", "    value = 2"), "body"),
        (MINIMAL.replace("    value: int", "    obj.value: int"), "body"),
        (MINIMAL.replace("    value: int", "    def method(self): pass"), "body"),
        (MINIMAL.replace("    value: int", "    value: factory()"), "calls"),
        (MINIMAL.replace("    value: int", "    value: list['Input']"), "forward"),
        (MINIMAL.replace("    value: int", "    value: Input"), "recursive"),
        (MINIMAL.replace("    value: int", "    value: Missing"), "ambiguous"),
        (
            MINIMAL.replace("    value: int", "    value: Required[int, str]"),
            "ambiguous",
        ),
        (MINIMAL.replace("    value: int", "    value: List[int]"), "earlier"),
        (
            MINIMAL.replace("(TypedDict)", "(TypedDict, total=bool(1))"),
            "literal boolean",
        ),
        (MINIMAL.replace("(TypedDict)", "(TypedDict, total=1)"), "literal boolean"),
        (MINIMAL.replace("(TypedDict)", "(TypedDict, metaclass=Meta)"), "metaclass"),
        (
            MINIMAL.replace("(TypedDict)", "(TypedDict, total=True, extra=True)"),
            "keywords",
        ),
        (MINIMAL.replace("(TypedDict)", "(TypedDict, Other)"), "inheritance"),
        (MINIMAL.replace("class Input", "@decorate\nclass Input"), "decorators"),
        (MINIMAL.replace("class Input", "TypedDict = Other\nclass Input"), "ambiguous"),
        (MINIMAL.replace("class Input", "del TypedDict\nclass Input"), "ambiguous"),
        (MINIMAL + "Input = Other\n", "binding"),
        (MINIMAL + "Input.__annotations__['value'] = str\n", "binding"),
        (
            MINIMAL.replace(
                "from typing import TypedDict",
                "from typing_extensions import TypedDict",
            ),
            "stdlib",
        ),
        (MINIMAL.replace("from typing import TypedDict", ""), "stdlib"),
        (
            MINIMAL.replace(
                "class Input(TypedDict):\n    value: int",
                'Input = TypedDict("Input", {"value": int})',
            ),
            "Functional",
        ),
        (
            MINIMAL.replace(
                "class Input(TypedDict):\n    value: int",
                'Input: object = TypedDict("Input", {"value": int})',
            ),
            "Functional",
        ),
        (
            MINIMAL.replace(
                "class Input(TypedDict):\n    value: int",
                "if True:\n    class Input(TypedDict):\n        value: int",
            ),
            "unconditional",
        ),
        (
            MINIMAL.replace(
                "class Input", "globals()['TypedDict'] = object\nclass Input"
            ),
            "ambiguous",
        ),
        (
            MINIMAL.replace("from typing import TypedDict", "from typing import *"),
            "stdlib",
        ),
        (
            MINIMAL.replace(
                "class Input", "class Base(TypedDict):\n    age: int\nclass Input"
            ).replace("class Input(TypedDict)", "class Input(Base)"),
            "inheritance",
        ),
    ],
)
def test_unsupported_declarations_are_explicit_and_never_exempt_initialization(
    source, problem
):
    inspected = inspect(source)
    evidence = next(
        d for d in inspected.readiness.structured_types if d.name == "Input"
    )
    assert evidence.type is None and problem in evidence.problem
    assessment = inspected.readiness.assessments[-1]
    assert not assessment.can_generate_interface
    assert Code.STRUCTURED_TYPE in {
        r.code for r in assessment.dimensions.inputs.reasons
    }
    assert Code.INITIALIZATION in {
        r.code for r in assessment.dimensions.execution.reasons
    }
    for renderer in (rest, mcp):
        with pytest.raises(GenerationRefused):
            renderer(inspected, source.encode(), select=["calculate"])


@pytest.mark.parametrize(
    "replacement",
    [
        "class Input:",
        "class Input(BaseModel):",
        "class Input(Config):",
        "class Input(Response):",
        "@dataclass\nclass Input:",
    ],
)
def test_ordinary_classes_are_not_typed_dicts(replacement):
    source = MINIMAL.replace("class Input(TypedDict):", replacement)
    inspected = inspect(source)
    assert inspected.readiness.structured_types == ()
    assessment = inspected.readiness.assessments[0]
    assert Code.INITIALIZATION in {
        r.code for r in assessment.dimensions.execution.reasons
    }
    assert Code.UNRESOLVED_TYPE in {
        r.code for r in assessment.dimensions.inputs.reasons
    }


@pytest.mark.parametrize(
    "prefix,suffix",
    [
        ("import typing\n", "typing.TypedDict = object\n"),
        ("import typing\n", "typing = object\n"),
        ("from typing import Required\n", "Required = object\n"),
        ("from typing import NotRequired\n", "del NotRequired\n"),
    ],
)
def test_rebound_markers_are_not_trusted(prefix, suffix):
    source = MINIMAL
    if "typing" in suffix:
        source = source.replace("from typing import TypedDict", prefix.strip()).replace(
            "(TypedDict)", "(typing.TypedDict)"
        )
    else:
        source = prefix + source.replace(
            "value: int",
            "value: "
            + ("NotRequired" if "NotRequired" in suffix else "Required")
            + "[int]",
        )
    source += suffix
    assert not inspect(source).readiness.assessments[0].can_generate_interface


def test_forward_class_and_function_annotations_are_bounded():
    source = (
        MINIMAL.replace("value: int", "value: Later")
        + "class Later(TypedDict):\n    n: int\n"
    )
    assert "Forward" in inspect(source).readiness.structured_types[0].problem
    source = (
        "from __future__ import annotations\ndef calculate(payload: Input): return payload\n"
        + MINIMAL.split("def calculate")[0]
    )
    assert not inspect(source).readiness.assessments[0].can_generate_interface


@pytest.mark.parametrize(
    "source",
    [
        "TypedDict = object\nclass Input(TypedDict):\n value: int",
        "if True:\n from typing import TypedDict\nclass Input(TypedDict):\n value: int",
        "class Input(TypedDict):\n value: int\nfrom typing import TypedDict",
        "from typing import TypedDict as TD\nTD = object\nclass Input(TD):\n value: int",
        "class Input(factory().TypedDict):\n value: int",
    ],
)
def test_authority_failures(source):
    source += "\ndef calculate(payload: Input): return payload\n"
    assert inspect(source).readiness.structured_types[0].type is None


def test_typing_marker_does_not_accept_arbitrary_syntax_or_bindings():
    facts = SourceFacts(ast.parse("def marker(): pass\n"))
    assert (
        facts.typing_marker(ast.parse("marker()", mode="eval").body, {"TypedDict"})
        is None
    )
    node = ast.parse("marker", mode="eval").body
    node.lineno = 2
    assert facts.typing_marker(node, {"TypedDict"}) is None
    facts = SourceFacts(ast.parse("from typing import Any\n"))
    node = ast.parse("Any", mode="eval").body
    node.lineno = 2
    assert facts.typing_marker(node, {"TypedDict"}) is None


@pytest.mark.parametrize("width,levels", [(1, 35), (2, 14)])
def test_deep_or_expanding_shapes_have_bounded_refusals(width, levels):
    source = "from typing import TypedDict\nclass T0(TypedDict):\n value: int\n"
    for index in range(1, levels):
        source += f"class T{index}(TypedDict):\n" + "".join(
            f" f{field}: T{index - 1}\n" for field in range(width)
        )
    source += f"def calculate(payload: T{levels - 1}): return payload\n"
    inspected = inspect(source)
    assert not inspected.readiness.assessments[0].can_generate_interface
    assert any(
        "bounded" in (d.problem or "") for d in inspected.readiness.structured_types
    )


def test_functional_non_name_targets_are_not_guessed():
    source = 'from typing import TypedDict\nobj.attr = TypedDict("Input", {"value": int})\nx = factory()\ndef calculate(payload: int): return payload\n'
    assert inspect(source).readiness.structured_types == ()


def test_generic_class_type_parameters_are_not_exempted_on_any_interpreter():
    tree = ast.parse(MINIMAL)
    node = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    # Python 3.11 cannot parse PEP 695 syntax; exercise the frozen AST guard
    # there too, rather than skipping this invariant on the oldest interpreter.
    node.type_params = [ast.Name(id="T", ctx=ast.Load())]
    evidence = declarations(SourceFacts(tree), "typed_sample")
    assert evidence[0].type is None and "Generic" in evidence[0].problem


@pytest.mark.parametrize(
    "owner,field,key",
    [
        ("Input", "__value", "_Input__value"),
        ("__Input", "__value", "_Input__value"),
        ("_", "__value", "__value"),
        ("Input", "__value__", "__value__"),
    ],
)
def test_private_class_field_names_use_frozen_python_mangling(owner, field, key):
    source = MINIMAL.replace("Input", owner).replace("value: int", field + ": int")
    shape = inspect(source).readiness.structured_types[0].type
    assert [f.name for f in shape.fields] == [key]


def test_mangled_name_collisions_are_duplicates():
    source = MINIMAL.replace("value: int", "__value: int\n    _Input__value: int")
    assert "Duplicate" in inspect(source).readiness.structured_types[0].problem


def test_non_structured_historical_bytes_are_unchanged():
    inspected = inspect("def calculate(value: int) -> int: return value * 2\n")
    assert b"structured_types" not in readiness_bytes(inspected.readiness)
    assert b"fields" not in json.dumps(TypeSpec(kind="int").model_dump()).encode()
    assert b"object" not in ir_bytes(inspected.capability_ir)
    assert (
        ReadinessReport.model_validate_json(readiness_bytes(inspected.readiness))
        == inspected.readiness
    )


@pytest.mark.parametrize(
    "kind,details",
    [
        ("object", {"items": [{"kind": "int"}]}),
        ("object", {"values": [1]}),
        ("object", {"variadic": True}),
        (
            "int",
            {"fields": [{"name": "value", "required": True, "type": {"kind": "int"}}]},
        ),
        (
            "object",
            {
                "fields": [
                    {"name": "bad-name", "required": True, "type": {"kind": "int"}}
                ]
            },
        ),
        (
            "object",
            {"fields": [{"name": "class", "required": True, "type": {"kind": "int"}}]},
        ),
        (
            "object",
            {"fields": [{"name": "value", "required": 1, "type": {"kind": "int"}}]},
        ),
    ],
)
def test_malformed_objects_and_model_construct_round_trip_are_rejected(kind, details):
    with pytest.raises(ValidationError):
        TypeSpec.model_validate({"kind": kind, **details})
    malformed = TypeSpec.model_construct(kind=kind, **details)
    with pytest.raises(ValidationError):
        TypeSpec.model_validate(malformed.model_dump(mode="json"))


@pytest.mark.parametrize(
    "spec",
    [
        TypeSpec(kind="list"),
        TypeSpec(kind="tuple", variadic=True),
        TypeSpec(kind="union"),
        TypeSpec(kind="literal"),
        TypeSpec(kind="int", items=(TypeSpec(kind="str"),)),
        TypeSpec(kind="int", values=(1,)),
        TypeSpec(kind="int", variadic=True),
    ],
)
def test_object_fields_require_valid_nested_contracts(spec):
    with pytest.raises(ValidationError):
        ObjectField(name="value", required=True, type=spec)


def test_structured_evidence_invariants_and_copy_rejection():
    evidence = inspect().readiness.structured_types[0]
    for details in (
        {"name": "Other"},
        {"type": None},
        {"problem": "bad"},
        {"type": TypeSpec(kind="int")},
    ):
        forged = evidence.model_copy(update=details)
        with pytest.raises(ValidationError):
            StructuredDeclaration.model_validate(forged.model_dump(mode="json"))
    report = inspect().readiness.model_copy(
        update={"structured_types": (evidence, evidence)}
    )
    with pytest.raises(ValidationError, match="Duplicate"):
        ReadinessReport.model_validate(report.model_dump(mode="json"))
    evidence = evidence.model_copy(
        update={"source": evidence.source.model_copy(update={"module": "other"})}
    )
    report = inspect().readiness.model_copy(update={"structured_types": (evidence,)})
    with pytest.raises(ValidationError, match="source modules"):
        ReadinessReport.model_validate(report.model_dump(mode="json"))


@given(st.permutations(["z", "a", "middle"]), st.booleans())
def test_field_order_is_semantically_canonical(order, required):
    fields = tuple(
        ObjectField(name=name, required=required, type=TypeSpec(kind="int"))
        for name in order
    )
    spec = TypeSpec(kind="object", fields=fields)
    assert [f.name for f in spec.fields] == ["a", "middle", "z"]
    assert json_schema(spec)["required"] == (["a", "middle", "z"] if required else [])
    assert (
        spec.model_dump_json()
        == TypeSpec(kind="object", fields=tuple(reversed(fields))).model_dump_json()
    )
