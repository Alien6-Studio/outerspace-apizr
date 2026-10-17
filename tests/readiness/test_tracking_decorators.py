"""SDK binding evidence never imports project code or blesses lookalike names."""

import ast

import pytest

from apizr.capabilities import inspect_source
from apizr.capabilities.instrumentation import TrackingBindings, is_tracking_import
from apizr.readiness import assess
from apizr.readiness.model import Code


@pytest.mark.parametrize(
    "imported,target",
    [
        ("from apizr.tracking import experiment", "experiment"),
        ("from apizr.tracking import experiment as capture", "capture"),
        ("import apizr.tracking as t", "t.experiment"),
        ("import apizr.tracking", "apizr.tracking.experiment"),
        ("from apizr import tracking", "tracking.experiment"),
        ("from apizr import tracking as t", "t.experiment"),
    ],
)
@pytest.mark.parametrize("configured", [False, True])
def test_proven_sdk_decorator_preserves_static_binding(imported, target, configured):
    decorator = (
        target
        + '(parameters=["value"], source="serving.py", distributions=("outerspace-apizr",), max_file_bytes=4096)'
        if configured
        else target
    )
    source = f"{imported}\n@{decorator}\ndef predict(value: int = 2) -> int:\n    return value * 3\n"
    ir = inspect_source(source, module_name="serving")
    assert ir.capabilities[0].availability.value == "unconditional"
    assert ir.capabilities[0].decorators[0].declared == decorator.replace('"', "'")
    report = assess(ir, source)
    decision = report.assessments[0]
    assert not decision.dimensions.binding.reasons
    assert {reason.code for reason in decision.dimensions.execution.reasons} == {
        Code.DEPENDENCY
    }
    assert not decision.can_generate_interface  # SDK wheel admission is still required.


@pytest.mark.parametrize(
    "source",
    [
        "def experiment(fn): return fn\n@experiment\ndef f(x: int): return x\n",
        "from other import experiment\n@experiment\ndef f(x: int): return x\n",
        "from apizr.tracking import experiment\nexperiment = other\n@experiment\ndef f(x: int): return x\n",
        "from apizr.tracking import experiment\n@experiment\ndef f(x: int): return x\nexperiment = other\n",
        "if enabled:\n    from apizr.tracking import experiment\n@experiment\ndef f(x: int): return x\n",
        "@experiment\ndef f(x: int): return x\nfrom apizr.tracking import experiment\n",
        "import apizr.tracking as t\nt.experiment = other\n@t.experiment\ndef f(x: int): return x\n",
        "import apizr.tracking as t\nt.__dict__['experiment'] = other\n@t.experiment\ndef f(x: int): return x\n",
        "from apizr.tracking import *\n@experiment\ndef f(x: int): return x\n",
        "from apizr.tracking import experiment\nglobals()\n@experiment\ndef f(x: int): return x\n",
        "from apizr.tracking import experiment\n__import__('other')\n@experiment\ndef f(x: int): return x\n",
        "from apizr.tracking import experiment\nlib.import_module('other')\n@experiment\ndef f(x: int): return x\n",
        "import apizr.tracking as t\n@t['experiment']\ndef f(x: int): return x\n",
        "from apizr import experiment\n@experiment\ndef f(x: int): return x\n",
        "from .apizr.tracking import experiment\n@experiment\ndef f(x: int): return x\n",
        "from apizr.tracking import experiment\n@other\n@experiment\ndef f(x: int): return x\n",
        "from apizr.tracking import experiment\n@experiment\n@experiment\ndef f(x: int): return x\n",
        "from apizr.tracking import experiment\nif enabled:\n    @experiment\n    def f(x: int): return x\n",
    ],
)
def test_unproven_or_stacked_decorator_remains_unknown(source):
    ir = inspect_source(source, module_name="serving")
    capability = next(c for c in ir.capabilities if c.name == "f")
    assert capability.availability.value == "unknown"
    decision = next(a for a in assess(ir, source).assessments if a.source.symbol == "f")
    assert Code.DECORATOR in {
        reason.code for reason in decision.dimensions.binding.reasons
    }
    assert not decision.can_generate_interface


@pytest.mark.parametrize(
    "configuration",
    [
        "parameters=names",
        'parameters=["missing"]',
        'parameters=["x", "x"]',
        "parameters=[1]",
        'parameters="x"',
        "parameters=[*names]",
        'parameters=["x"] * 257',
        'parameters=["x"], parameters=[]',
        'root=Path(".")',
        "store=object()",
        "source=source",
        "source=1",
        "unknown=True",
        "**configuration",
        "None",
        "distributions=names",
        "distributions=[1]",
        "distributions=[*names]",
        "max_file_bytes=True",
        "max_file_bytes=0",
        "max_file_bytes=2**40",
    ],
)
def test_dynamic_or_invalid_configuration_does_not_gain_inertness(configuration):
    source = f"from apizr.tracking import experiment\n@experiment({configuration})\ndef f(x: int) -> int:\n    return x\n"
    ir = inspect_source(source, module_name="serving")
    assert ir.capabilities[0].availability.value == "unknown"
    reasons = assess(ir, source).assessments[0].dimensions.execution.reasons
    assert Code.INITIALIZATION in {reason.code for reason in reasons}


def test_other_definition_time_calls_and_module_effects_stay_visible(tmp_path):
    sentinel = tmp_path / "executed"
    source = f"""from apizr.tracking import experiment
open({str(sentinel)!r}, 'w').write('executed')
@experiment(parameters=['x'], root=None, store=None, source=None, distributions=[])
def f(x: int = side_effect()) -> int:
    return x
"""
    ir = inspect_source(source, module_name="serving")
    reasons = assess(ir, source).assessments[0].dimensions.execution.reasons
    assert {r.line for r in reasons if r.code == Code.INITIALIZATION} == {2, 4}
    assert not sentinel.exists()


@pytest.mark.parametrize(
    "imported,expected",
    [
        ("import apizr.tracking", True),
        ("import apizr.tracking.session", True),
        ("from apizr.tracking import experiment", True),
        ("from apizr.tracking.session import TrackingError", True),
        ("from apizr import tracking", True),
        ("from apizr import other", False),
        ("import apizr", False),
        ("from apizr.tracking_extra import experiment", False),
        ("from .apizr.tracking import experiment", False),
    ],
)
def test_dependency_detection_uses_imports_only(imported, expected):
    node = ast.parse(imported).body[0]
    assert (
        is_tracking_import(
            module=getattr(node, "module", None),
            names=tuple(a.name for a in node.names),
            relative_level=getattr(node, "level", 0),
        )
        == expected
    )


def test_sdk_calls_retain_exact_import_bindings():
    tree = ast.parse("import apizr.tracking as t\nt.log_metric('score', 1)\n")
    assert TrackingBindings(tree).member(tree.body[1].value.func) == "log_metric"


def test_large_ast_is_not_promoted_by_partial_binding_analysis():
    tree = ast.parse(
        "from apizr.tracking import experiment\n@experiment\ndef f(): pass\n"
    )
    tree.body.extend(ast.Expr(value=ast.Constant(value=0)) for _ in range(100_000))
    assert not TrackingBindings(tree).inert_decorator(tree.body[1])


@pytest.mark.parametrize(
    "imported,target",
    [
        ("from apizr.tracking import experiment", "experiment"),
        ("import apizr.tracking as t", "t.experiment"),
        ("from apizr import tracking as t", "t.experiment"),
    ],
)
def test_repository_local_sdk_lookalike_cannot_discharge_dependency(imported, target):
    from apizr.graph import build_graph
    from apizr.repository import scan_sources
    from apizr.repository_readiness import assess_repository
    from apizr.repository_readiness.eligibility import can_generate_interface

    sources = {
        "apizr/__init__.py": b"",
        "apizr/tracking.py": b"def experiment(function): return function\n",
        "serving.py": f"{imported}\n@{target}\ndef f(x: int) -> int: return x\n".encode(),
    }
    catalog = scan_sources(sources.items())
    graph = build_graph(catalog, sources)
    report = assess_repository(catalog, graph)
    decision = next(
        a for a in report.assessments if a.capability_id == "python:serving:f"
    )
    assert not can_generate_interface(decision)


@pytest.mark.parametrize("body", ["yield x", "yield from x"])
def test_sdk_generator_is_not_an_inert_import_binding(body):
    source = (
        f"from apizr.tracking import experiment\n@experiment\ndef f(x):\n    {body}\n"
    )
    ir = inspect_source(source, module_name="serving")
    assert ir.capabilities[0].availability.value == "unknown"
    assert not assess(ir, source).assessments[0].can_generate_interface


def test_yield_in_nested_definition_default_belongs_to_outer_generator():
    source = """from apizr.tracking import experiment
@experiment
def f(x):
    def inner(value=(yield x)): return value
    return inner
"""
    ir = inspect_source(source, module_name="serving")
    assert ir.capabilities[0].execution == "generator"
    assert ir.capabilities[0].availability.value == "unknown"


@pytest.mark.parametrize(
    "statement",
    [
        "try:\n    pass\nexcept Exception as experiment:\n    pass",
        "match value:\n    case {'key': experiment}: pass",
        "match value:\n    case [*experiment]: pass",
        "match value:\n    case {'key': _, **experiment}: pass",
        "experiment = lambda x=other(): x",
        "def other(x=(experiment := value)): pass",
        "class experiment: pass",
    ],
)
def test_other_module_binding_forms_do_not_establish_sdk_identity(statement):
    source = f"from apizr.tracking import experiment\n{statement}\n@experiment\ndef f(x): return x\n"
    ir = inspect_source(source, module_name="serving")
    assert (
        next(c for c in ir.capabilities if c.name == "f").availability.value
        == "unknown"
    )
