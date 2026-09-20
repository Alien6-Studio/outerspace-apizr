import pytest

from apizr.inspection import inspect_source
from apizr.readiness.model import Code, State


@pytest.mark.parametrize(
    "annotation",
    [
        "int",
        "str",
        "bool",
        "float",
        "None",
        "list[int]",
        "set[str]",
        "tuple[int, str]",
        "tuple[int, ...]",
        "dict[str, list[int]]",
        "int | None",
        "Union[int, str]",
        "Optional[int]",
        'Literal["a", "b", 1, True, None]',
        "typing.List[int]",
        "Literal[-1, +2, -1.5]",
        "Any",
        "list",
        "dict",
        "tuple",
        "set",
    ],
)
def test_supported_syntactic_json_contracts(annotation):
    value = inspect_source(
        f"def f(x: {annotation}): pass", module_name="types"
    ).readiness.assessments[0]
    assert value.dimensions.inputs.state == State.READY
    assert value.can_generate_interface


@pytest.mark.parametrize(
    ("annotation", "state", "code"),
    [
        ("Callable", State.UNSUPPORTED, Code.NON_JSON),
        ("Callable[[int], str]", State.UNSUPPORTED, Code.NON_JSON),
        ("list[Callable]", State.UNSUPPORTED, Code.NON_JSON),
        ("bytes", State.UNSUPPORTED, Code.NON_JSON),
        ("dict[int, str]", State.UNSUPPORTED, Code.NON_JSON),
        ('Literal[b"bytes"]', State.UNSUPPORTED, Code.NON_JSON),
        ("Literal[factory()]", State.UNSUPPORTED, Code.NON_JSON),
        ("Literal[-1e999]", State.UNSUPPORTED, Code.NON_JSON),
        ("Literal[-True]", State.UNSUPPORTED, Code.NON_JSON),
        ("Literal[1e999]", State.UNSUPPORTED, Code.NON_JSON),
        ('"Missing"', State.CONDITIONAL, Code.UNRESOLVED_TYPE),
        ("User", State.CONDITIONAL, Code.UNRESOLVED_TYPE),
        ("SomeLibrary.Type[X]", State.CONDITIONAL, Code.UNRESOLVED_TYPE),
        ("unknown()", State.CONDITIONAL, Code.UNRESOLVED_TYPE),
        ("Annotated[int, Field(gt=0)]", State.CONDITIONAL, Code.METADATA),
        ("list[int, str]", State.CONDITIONAL, Code.UNRESOLVED_TYPE),
        ("dict[str]", State.CONDITIONAL, Code.UNRESOLVED_TYPE),
        ("Optional[int, str]", State.CONDITIONAL, Code.UNRESOLVED_TYPE),
    ],
)
def test_inputs_do_not_invent_runtime_or_adapter_semantics(annotation, state, code):
    value = inspect_source(
        f"def f(x: {annotation}): pass", module_name="types"
    ).readiness.assessments[0]
    assert value.dimensions.inputs.state == state
    assert code in {r.code for r in value.dimensions.inputs.reasons}
    assert not value.can_generate_interface


@pytest.mark.parametrize(
    "source",
    [
        "from typing import List as List\ndef f(x: List[int]): pass",
        "import typing as t\ndef f(x: t.List[int]): pass",
        'from typing import Literal, Optional\ndef f(x: Optional[Literal["a"]]): pass',
    ],
)
def test_unique_typing_import_aliases(source):
    assert (
        inspect_source(source, module_name="alias").readiness.assessments[0].state
        == State.READY
    )


@pytest.mark.parametrize(
    "source",
    [
        "int = custom\ndef f(x: int): pass",
        "from other import int\ndef f(x: int): pass",
        "from .typing import List\ndef f(x: List[int]): pass",
        "if True:\n from typing import List\ndef f(x: List[int]): pass",
        "import typing\ntyping = custom\ndef f(x: typing.List[int]): pass",
        "import other as typing\ndef f(x: typing.List[int]): pass",
        "import typing\ntyping.List = 42\ndef f(x: typing.List[int]): pass",
        "import typing as t\ndel t.List\ndef f(x: t.List[int]): pass",
        "from typing import List as L\nL[0] = 42\ndef f(x: L[int]): pass",
        "import typing\ntyping.List.attr = 42\ndef f(x: typing.List[int]): pass",
        "from typing import str\ndef f(x: str): pass",
        "import typing\ndef f(x: typing.int): pass",
        "class User: pass\ndef f(x: User): pass",
    ],
)
def test_shadowed_and_application_types_are_uncertain(source):
    value = next(
        a
        for a in inspect_source(source, module_name="shadow").readiness.assessments
        if a.source.symbol == "f"
    )
    assert value.dimensions.inputs.state == State.CONDITIONAL


@pytest.mark.parametrize(
    "annotation", ["Callable", "bytes", "Missing", '"Missing"', "list[User]"]
)
def test_unresolved_or_non_json_returns_do_not_alone_block_exposure(annotation):
    result = inspect_source(
        f"def f(x: int) -> {annotation}: pass", module_name="output"
    )
    value = result.readiness.assessments[0]
    assert value.state == State.READY and value.can_generate_interface
    assert [r.code for r in value.dimensions.outputs.reasons] == [Code.OUTPUT]
    assert result.capability_ir.capabilities[0].signature.returns.enforcement == "none"


def test_missing_annotations_are_explicitly_unconstrained_not_inferred_from_default():
    result = inspect_source("def f(x=1): pass", module_name="untyped")
    value = result.readiness.assessments[0]
    assert value.state == State.READY
    assert [(r.code, r.parameter) for r in value.dimensions.inputs.reasons] == [
        (Code.UNCONSTRAINED, "x")
    ]
    assert (
        result.capability_ir.capabilities[0].signature.parameters[0].annotation is None
    )
