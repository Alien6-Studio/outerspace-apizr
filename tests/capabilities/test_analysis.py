"""New expectations against shared source evidence, not legacy metadata."""

import json
from pathlib import Path

import pytest

from apizr.capabilities import inspect_source
from apizr.capabilities.model import DiagnosticCode, ExecutionForm, Severity
from apizr.capabilities.types import Evidence

CORPUS = Path(__file__).resolve().parents[1] / "fixtures/characterization"
DISCOVERY = json.loads((CORPUS / "discovery.json").read_text())
EXPECTED = {
    "top_level_function": (["first", "second"], []),
    "async_function": (["work"], []),
    "mixed_parameters": (["call"], []),
    "unicode_identifiers": (["café"], []),
    "long_identifier": (["function_" + "x" * 200], []),
    "decorators": (["work"], ["APIZR-CAP-005"]),
    "variadic_args": ([], ["APIZR-CAP-002"]),
    "variadic_kwargs": ([], ["APIZR-CAP-002"]),
    "variadic_both": ([], ["APIZR-CAP-002"]),
    "lambda": ([], ["APIZR-CAP-005"]),
    "nested_closure": (["outer"], []),
    "methods": ([], []),
    "generator": (["items"], []),
    "async_generator": (["items"], []),
    "overloads": (["call"], []),
    "duplicate_definitions": ([], ["APIZR-CAP-001"]),
    "conditional_definition": (["unavailable"], ["APIZR-CAP-003"]),
    "keywords_in_data": (["real"], []),
}


@pytest.mark.parametrize("case", DISCOVERY, ids=lambda c: c["id"])
def test_discovery_corpus(case):
    document = inspect_source(case["source"], module_name="corpus")
    names, codes = EXPECTED[case["id"]]
    assert [c.name for c in document.capabilities] == names
    assert [d.code.value for d in document.diagnostics] == codes
    for capability in document.capabilities:
        assert capability.id == f"python:corpus:{capability.name}"
        assert capability.evidence == Evidence.OBSERVED
        assert capability.signature.returns.enforcement == "none"
        assert all(
            v == {"value": "unknown", "evidence": "unknown"}
            for v in capability.effects.model_dump(mode="json").values()
        )


def test_parameters_defaults_and_docstrings_are_independent():
    capability = inspect_source(
        '''def call(a, /, b: int = None, *, c: int | None = None, d: "User") -> str:
    """First line.

    Body.
    """
    return ""
''',
        module_name="contracts",
    ).capabilities[0]
    a, b, c, d = capability.signature.parameters
    assert (a.name, a.kind, a.required, a.default, a.annotation) == (
        "a",
        "positional_only",
        True,
        None,
        None,
    )
    assert (b.kind, b.required, b.default.declared, b.annotation.declared) == (
        "positional_or_keyword",
        False,
        "None",
        "int",
    )
    assert (c.kind, c.required, c.default.declared, c.annotation.declared) == (
        "keyword_only",
        False,
        "None",
        "int | None",
    )
    assert (d.kind, d.required, d.default, d.annotation.declared) == (
        "keyword_only",
        True,
        None,
        "'User'",
    )
    assert capability.docstring == "First line.\n\nBody."
    assert capability.signature.returns.annotation.declared == "str"
    assert capability.availability.value == "unconditional"
    assert capability.source.line == 1 and capability.source.end_line == 6


@pytest.mark.parametrize(
    ("source", "form"),
    [
        ("def f(): return 1", ExecutionForm.SYNC),
        ("async def f(): return 1", ExecutionForm.ASYNC),
        ("def f(): yield 1", ExecutionForm.GENERATOR),
        ("def f(): yield from other", ExecutionForm.GENERATOR),
        ("async def f(): yield 1", ExecutionForm.ASYNC_GENERATOR),
        ("def f():\n def inner(): yield 1\n return inner", ExecutionForm.SYNC),
        (
            "async def f():\n async def inner(): yield 1\n return inner",
            ExecutionForm.ASYNC,
        ),
        (
            "def f():\n class Inner:\n  def g(self): yield 1\n return Inner",
            ExecutionForm.SYNC,
        ),
        ("def f():\n return lambda: (yield 1)", ExecutionForm.SYNC),
    ],
)
def test_execution_form_uses_own_scope(source, form):
    document = inspect_source(source, module_name="forms")
    assert len(document.capabilities) == 1
    assert document.capabilities[0].execution == form


@pytest.mark.parametrize(
    "prefix",
    [
        "if False:",
        "if True:",
        "for x in []:",
        "while False:",
        "with context():",
        "try:",
        "match value:\n case 1:",
    ],
)
def test_control_flow_is_never_claimed_available(prefix):
    indent = "  " if prefix.startswith("match") else " "
    source = prefix + "\n" + indent + "def work(): pass\n"
    if prefix == "try:":
        source += "except Exception: pass\n"
    document = inspect_source(source, module_name="flow")
    assert document.capabilities[0].availability.model_dump() == {
        "value": "unknown",
        "evidence": Evidence.UNKNOWN,
    }
    assert document.diagnostics[0].code == DiagnosticCode.CONDITIONAL
    assert document.diagnostics[0].severity == Severity.WARNING


def test_decorators_preserve_calls_without_semantics():
    document = inspect_source(
        "@cache\n@transactional(read_only=True)\ndef run(): pass",
        module_name="decorated",
    )
    capability = document.capabilities[0]
    assert [d.declared for d in capability.decorators] == [
        "cache",
        "transactional(read_only=True)",
    ]
    assert capability.availability.value == "unknown"
    assert capability.docstring is None
    assert document.diagnostics[0].source.symbol == "run"


@pytest.mark.parametrize(
    ("preamble", "marker"),
    [
        ("from typing import overload", "overload"),
        ("from typing import overload as contract", "contract"),
        ("import typing", "typing.overload"),
        ("import typing as t", "t.overload"),
    ],
)
def test_overloads_are_contracts_for_one_implementation(preamble, marker):
    document = inspect_source(
        f"{preamble}\n@{marker}\ndef f(x: int) -> int: ...\n@{marker}\ndef f(x: str) -> str: ...\ndef f(x): return x\n",
        module_name="overloads",
    )
    assert document.diagnostics == ()
    (capability,) = document.capabilities
    assert capability.signature.parameters[0].annotation is None
    assert [
        o.signature.parameters[0].annotation.declared for o in capability.overloads
    ] == ["int", "str"]
    assert [o.source.line for o in capability.overloads] == [3, 5]
    assert capability.source.line == 6


@pytest.mark.parametrize(
    "source",
    [
        "from typing import overload\n@overload\ndef f(): ...",
        "@overload\ndef f(): ...\ndef f(): pass",
        "@other.overload\ndef f(): ...\ndef f(): pass",
        "@package.typing.overload\ndef f(): ...\ndef f(): pass",
        "from typing import overload\ndef f(): pass\n@overload\ndef f(): ...",
        "from typing import overload\n@overload\ndef f(): ...\nx = 1\ndef f(): pass",
        "from typing import overload\n@overload\n@other\ndef f(): ...\ndef f(): pass",
        "from typing import overload\n@overload\ndef f(): ...\nasync def f(): pass",
        "from typing import overload\nif True:\n @overload\n def f(): ...\n def f(): pass",
        "if True:\n from typing import overload\n@overload\ndef f(): ...\ndef f(): pass",
        "@typing.overload\ndef f(): ...\ndef f(): pass\nimport typing",
        "from .typing import overload\n@overload\ndef f(): ...\ndef f(): pass",
        "import typing\n@typing\ndef ordinary(): pass\n@typing.overload\ndef f(): ...",  # ordinary decorator isn't a marker
        "from typing import overload as t\n@t.overload\ndef f(): ...\ndef f(): pass",
    ],
)
def test_ambiguous_overloads_never_select_a_stub(source):
    document = inspect_source(source, module_name="ambiguous")
    assert "f" not in [c.name for c in document.capabilities]
    assert any(
        d.code == DiagnosticCode.OVERLOAD and d.severity == Severity.ERROR
        for d in document.diagnostics
    )


@pytest.mark.parametrize(
    "rebind",
    [
        "overload = replacement",
        "del overload",
        "def overload(): pass",
        "class overload: pass",
        "from other import overload",
        "import other as overload",
        "try: pass\nexcept Exception as overload: pass",
        "match value:\n case overload: pass",
        "match value:\n case [*overload]: pass",
        "match value:\n case {**overload}: pass",
        "def other(x=(overload := replacement)): pass",
    ],
)
def test_rebound_overload_markers_are_not_trusted(rebind):
    source = (
        f"from typing import overload\n{rebind}\n@overload\ndef f(): ...\ndef f(): pass"
    )
    document = inspect_source(source, module_name="binding")
    assert "f" not in [c.name for c in document.capabilities]
    assert any(d.code == DiagnosticCode.OVERLOAD for d in document.diagnostics)


def test_variadic_overload_contract_invalidates_symbol():
    document = inspect_source(
        "from typing import overload\n@overload\ndef f(*args): ...\ndef f(x): return x",
        module_name="contracts",
    )
    assert not document.capabilities
    assert [d.code for d in document.diagnostics] == [DiagnosticCode.VARIADIC]


def test_annotated_lambda_is_diagnosed_and_nested_scopes_stay_out():
    document = inspect_source(
        "call: Callable = lambda: 1\nclass Service:\n callback = lambda: 2\n",
        module_name="lambdas",
    )
    assert document.capabilities == ()
    assert [(d.source.symbol, d.code) for d in document.diagnostics] == [
        ("call", DiagnosticCode.BINDING)
    ]
