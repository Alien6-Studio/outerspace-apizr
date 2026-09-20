import json
from pathlib import Path

import pytest

from apizr.inspection import inspect_source
from apizr.readiness.model import Code, State


def assessment(source, name="f"):
    result = inspect_source(source, module_name="example")
    return next(a for a in result.readiness.assessments if a.source.symbol == name)


def codes(value):
    return {
        r.code
        for dimension in (
            value.dimensions.binding,
            value.dimensions.execution,
            value.dimensions.inputs,
            value.dimensions.outputs,
        )
        for r in dimension.reasons
    }


@pytest.mark.parametrize(
    "source",
    [
        "def f(x: int) -> int: return x",
        "async def f(x: int) -> int: return x",
        "def f(): return 1",
        "def f(x, y=None): return x",
        "value = [1, {'x': -2}]\ndef f(x: int = 1, /, *, y: str = 'x'): pass",
        "import math\ndef f(x: float): return math.sqrt(x)",
        "def other(): dangerous()\ndef f(): pass",
        "def f(): pass\nf: int",
        "from typing import overload\n@overload\ndef f(x: int) -> int: ...\n@overload\ndef f(x: str) -> str: ...\ndef f(x): return x",
    ],
)
def test_ready_means_contract_eligible_not_runtime_safe(source):
    value = assessment(source)
    assert value.state == State.READY
    assert value.can_generate_interface
    assert all(
        v == {"value": "unknown", "evidence": "unknown"}
        for v in value.effects.model_dump(mode="json").values()
    )


@pytest.mark.parametrize(
    ("source", "state", "code"),
    [
        ("def f(): yield 1", State.UNSUPPORTED, Code.GENERATOR),
        ("async def f(): yield 1", State.UNSUPPORTED, Code.ASYNC_GENERATOR),
        ("@cache\ndef f(): pass", State.CONDITIONAL, Code.DECORATOR),
        ("if False:\n def f(): pass", State.CONDITIONAL, Code.CONDITIONAL),
        ("def f(*args): pass", State.UNSUPPORTED, Code.VARIADIC),
        ("def f(**kwargs): pass", State.UNSUPPORTED, Code.VARIADIC),
        ("def f(): pass\ndef f(): pass", State.AMBIGUOUS, Code.DUPLICATE),
        (
            "from typing import overload\n@overload\ndef f(): ...",
            State.AMBIGUOUS,
            Code.OVERLOAD,
        ),
        ("f = lambda: 1", State.UNSUPPORTED, Code.CONSTRUCT),
        (
            "raise RuntimeError('never run')\ndef f(): pass",
            State.CONDITIONAL,
            Code.INITIALIZATION,
        ),
        ("initialize()\ndef f(): pass", State.CONDITIONAL, Code.INITIALIZATION),
        ("value = initialize()\ndef f(): pass", State.CONDITIONAL, Code.INITIALIZATION),
        (
            "def f(): pass\nraise RuntimeError('later abort')",
            State.CONDITIONAL,
            Code.INITIALIZATION,
        ),
        ("def f(x=initialize()): pass", State.CONDITIONAL, Code.INITIALIZATION),
        ("def f(x=1/0): pass", State.CONDITIONAL, Code.INITIALIZATION),
        ("def f(x: unknown()): pass", State.CONDITIONAL, Code.UNRESOLVED_TYPE),
    ],
)
def test_blockers_and_uncertainty_are_explicit(source, state, code):
    result = inspect_source(source, module_name="example")
    value = result.readiness.assessments[0]
    assert value.state == state
    assert not value.can_generate_interface
    assert code in codes(value)
    assert result.exit_code == (
        1 if state in {State.UNSUPPORTED, State.AMBIGUOUS} else 0
    )


@pytest.mark.parametrize(
    "statement",
    [
        "f = replacement",
        "f: object = replacement",
        "f += replacement",
        "del f",
        "class f: pass",
        "import math as f",
        "from math import sin as f",
        "for f in []: pass",
        "with context() as f: pass",
        "try: pass\nexcept Exception as f: pass",
        "match value:\n case f: pass",
        "match value:\n case [*f]: pass",
        "match value:\n case {**f}: pass",
        "(f := replacement)",
        "if False:\n f = replacement",
        "def other(x=(f := 1)): pass",
        "def other(*, x=(f := 1)): pass",
        "callback = lambda x=(f := 1): x",
        "class Other((f := Base)): pass",
        "items = [(f := item) for item in []]",
    ],
)
def test_later_module_bindings_are_never_ignored(statement):
    value = assessment("def f(x: int): return x\n" + statement)
    assert value.dimensions.binding.state == State.CONDITIONAL
    assert Code.REBOUND in codes(value)
    assert not value.can_generate_interface


@pytest.mark.parametrize(
    "statement",
    [
        "items = [f for f in []]",
        "items = {f for f in []}",
        "items = {f: f for f in []}",
        "def other():\n f = 1",
        "class Other:\n f = 1",
        "callback = lambda f: f",
    ],
)
def test_nested_local_names_do_not_rebind_module_function(statement):
    value = assessment("def f(): pass\n" + statement)
    assert value.dimensions.binding.state == State.READY
    assert Code.REBOUND not in codes(value)


@pytest.mark.parametrize(
    "statement",
    [
        "with context(): pass",
        "for x in []: pass",
        "while condition: pass",
        "try: pass\nexcept Exception: pass",
        "value = a + b",
        "class Other: pass",
        "@decorate\ndef other(): pass",
        "x: annotation()",
        "x = {**other}",
    ],
)
def test_bounded_initialization_policy_identifies_execution_bearing_statements(
    statement,
):
    value = assessment(statement + "\ndef f(): pass")
    assert Code.INITIALIZATION in codes(value)
    assert value.dimensions.execution.state == State.CONDITIONAL


@pytest.mark.parametrize(
    "statement",
    [
        "globals()['f'] = replacement",
        "locals().update({'f': replacement})",
        "vars().update({'f': replacement})",
        "exec(code)",
        "eval(code)",
        "from somewhere import *",
    ],
)
def test_dynamic_namespace_is_uncertain(statement):
    value = assessment("def f(): pass\n" + statement)
    assert Code.NAMESPACE in codes(value)
    assert value.dimensions.binding.state == State.CONDITIONAL


@pytest.mark.parametrize(
    "source",
    [
        "__import__('unknown')\ndef f(): pass",
        "import importlib\ndef f(): return importlib.import_module('unknown')",
        "from importlib import import_module as load\ndef f(): return load('unknown')",
        "def f():\n from importlib import import_module as load\n return load('unknown')",
    ],
)
def test_dynamic_imports_are_reported_without_resolution(source):
    assert Code.DYNAMIC_IMPORT in codes(assessment(source))


@pytest.mark.parametrize(
    "source",
    [
        "import unresolved_local\ndef f(): pass",
        "from .helper import value\ndef f(): pass",
        "from package.namespace import value\ndef f(): pass",
        "def f():\n import external\n return external.value",
    ],
)
def test_dependency_uncertainty_does_not_search_or_import(source):
    assert Code.DEPENDENCY in codes(assessment(source))


CORPUS = json.loads(
    (
        Path(__file__).resolve().parents[1] / "fixtures/characterization/discovery.json"
    ).read_text()
)


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c["id"])
def test_shared_discovery_inputs_have_consistent_assessment_membership(case):
    inspection = inspect_source(case["source"], module_name="corpus")
    members = {c.id for c in inspection.capability_ir.capabilities}
    assert {
        a.capability_id for a in inspection.readiness.assessments if a.in_ir
    } == members
    assert len({a.capability_id for a in inspection.readiness.assessments}) == len(
        inspection.readiness.assessments
    )
    if case["id"] in {
        "duplicate_definitions",
        "overloads",
        "generator",
        "async_generator",
    }:
        expected = {
            "duplicate_definitions": State.AMBIGUOUS,
            "overloads": State.READY,
            "generator": State.UNSUPPORTED,
            "async_generator": State.UNSUPPORTED,
        }
        assert inspection.readiness.assessments[0].state == expected[case["id"]]
