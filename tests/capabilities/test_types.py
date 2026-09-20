import ast
import json
from pathlib import Path

import pytest

from apizr.capabilities import inspect_source
from apizr.capabilities.model import DiagnosticCode
from apizr.capabilities.types import Evidence, TypeForm

CORPUS = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "fixtures/characterization/annotations.json"
    ).read_text()
)


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c["id"])
def test_every_characterized_annotation_preserves_its_complete_expression(case):
    expression = case["expression"]
    source = (
        case.get("preamble", "")
        + f"def function(value: {expression}) -> {expression}: pass\n"
    )
    capability = inspect_source(source, module_name="types").capabilities[0]
    annotation = capability.signature.parameters[0].annotation
    assert annotation.evidence == Evidence.DECLARED
    # Structural equality includes values, nested members and metadata, not just names.
    assert ast.dump(ast.parse(annotation.declared, mode="eval")) == ast.dump(
        ast.parse(expression, mode="eval")
    )
    assert capability.signature.returns.annotation == annotation


@pytest.mark.parametrize(
    ("expression", "normalized", "form"),
    [
        ('Literal["a"]', "Literal['a']", TypeForm.SUBSCRIPT),
        ('Literal["b"]', "Literal['b']", TypeForm.SUBSCRIPT),
        ('"User"', "'User'", TypeForm.FORWARD_REFERENCE),
        ('"Other"', "'Other'", TypeForm.FORWARD_REFERENCE),
        ("list[int] | list[str]", "list[int] | list[str]", TypeForm.UNION),
        ("list[int] | None", "list[int] | None", TypeForm.UNION),
        ("tuple[int, str]", "tuple[int, str]", TypeForm.SUBSCRIPT),
        (
            "Annotated[int, Field(gt=0)]",
            "Annotated[int, Field(gt=0)]",
            TypeForm.SUBSCRIPT,
        ),
        ("Callable[[int], str]", "Callable[[int], str]", TypeForm.SUBSCRIPT),
        (
            "SomeLibrary.SpecialType[X]",
            "SomeLibrary.SpecialType[X]",
            TypeForm.SUBSCRIPT,
        ),
        ("typing.List", "typing.List", TypeForm.ATTRIBUTE),
        ("User", "User", TypeForm.NAME),
        ("None", "None", TypeForm.LITERAL),
        ("unknown()", "unknown()", TypeForm.UNKNOWN),
        ("A + B", "A + B", TypeForm.UNKNOWN),
    ],
)
def test_declarations_are_distinct_even_without_runtime_resolution(
    expression, normalized, form
):
    document = inspect_source(f"def f(x: {expression}): pass", module_name="types")
    annotation = document.capabilities[0].signature.parameters[0].annotation
    assert annotation.declared == normalized
    assert annotation.form == form
    assert [d.code for d in document.diagnostics] == (
        [DiagnosticCode.TYPE_STRUCTURE] if form == TypeForm.UNKNOWN else []
    )


def test_future_annotations_and_aliases_are_not_resolved():
    source = 'from __future__ import annotations\nAlias = side_effect()\ndef f(x: Alias, y: "Missing") -> unknown(): pass'
    capability = inspect_source(source, module_name="future").capabilities[0]
    assert [p.annotation.declared for p in capability.signature.parameters] == [
        "Alias",
        "'Missing'",
    ]
    assert capability.signature.returns.annotation.declared == "unknown()"
