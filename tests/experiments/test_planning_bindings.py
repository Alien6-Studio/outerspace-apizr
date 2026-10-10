"""Pure intent and conservative correlation never turn syntax into runtime truth."""

import pytest

from apizr.experiments.bindings import automatic_metrics
from apizr.experiments.inspection import inspect_experiment
from apizr.experiments.metrics import discover_metrics
from apizr.experiments.outputs import parse_output_declaration
from apizr.experiments.planning import RunOptions, derive_plan, parse_metric_binding
from apizr.experiments.serialization import plan_bytes, plan_digest


def inspect(tmp_path, source):
    path = tmp_path / "train.py"
    path.write_text(source)
    return inspect_experiment(path)


def test_pure_plan_preserves_identities_and_omits_conflicting_candidates(tmp_path):
    inspection = inspect(
        tmp_path,
        """import random
random.seed(42)
rate = 0.1
rate = 0.2
same = {"a": 1, "b": 2}
same = {"b": 2, "a": 1}
unknown = object()
raise RuntimeError("must never execute")
""",
    )
    plan = derive_plan(inspection)
    assert plan.subject.capability_id is None
    assert plan.subject.digest == inspection.code.source.digest.value
    assert plan.subject.executable_digest == plan.subject.digest
    assert [p.name for p in plan.parameters] == ["same"]
    assert plan.inputs == inspection.data.artifacts
    assert plan.randomness == inspection.randomness.controls
    assert plan.environment == inspection.environment.evidence
    assert plan_digest(plan) == plan_digest(derive_plan(inspection))
    assert str(tmp_path).encode() not in plan_bytes(plan)
    controls = {p.name: p.value for p in plan.execution.controls}
    assert controls["filesystem"] == controls["network"] == "host"
    assert controls["subprocess"] == "allowed"
    assert controls["environment"] == "clean"


@pytest.mark.parametrize(
    "options",
    [
        RunOptions(timeout_ms=200),
        RunOptions(inherit_environment=True),
        RunOptions(environment_names=("TOKEN",)),
        RunOptions(max_output_bytes=17),
        RunOptions(metrics=(parse_metric_binding("auc=result"),)),
        RunOptions(outputs=(parse_output_declaration("model=model.bin"),)),
    ],
)
def test_controls_bind_plan_digest(tmp_path, options):
    result = inspect(tmp_path, "x = 1")
    assert plan_digest(derive_plan(result, execution=options)) != plan_digest(
        derive_plan(result)
    )
    assert RunOptions(environment_names=("B", "A", "B")).environment_names == ("A", "B")


@pytest.mark.parametrize(
    "value", ["x", "=x", "x=", "x=a.b", "x=f()", "x=class", "x=a[0]", "x= x", "x=a=b"]
)
def test_metric_selectors_are_identifiers_not_expressions(value):
    with pytest.raises(ValueError, match="metric_binding_invalid"):
        parse_metric_binding(value)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout_ms": 0},
        {"timeout_ms": 3600001},
        {"timeout_ms": True},
        {"environment_names": ("A=B",)},
        {"environment_names": ("É",)},
        {"environment_names": ("A",), "inherit_environment": True},
        {"metrics": (parse_metric_binding("a=x"), parse_metric_binding("a=y"))},
        {"outputs": (parse_output_declaration("a=x"), parse_output_declaration("a=y"))},
        {"max_output_bytes": 0},
        {"surprise": True},
    ],
)
def test_invalid_run_controls_refused(kwargs):
    with pytest.raises(ValueError):
        RunOptions(**kwargs)


def binding(source):
    result = discover_metrics(source, source_reference="train.py")
    return automatic_metrics(source, result)


@pytest.mark.parametrize(
    "assignment", ["result = metric(y, p)", "result: float = metric(y, p)"]
)
def test_automatic_metrics_use_existing_signal_authority(assignment):
    source = "from sklearn.metrics import roc_auc_score as metric\n" + assignment
    assert binding(source) == (parse_metric_binding("roc_auc=result"),)


@pytest.mark.parametrize(
    "fragment",
    [
        "result = object()",
        "result += 1",
        "del result",
        "def result(): pass",
        "async def result(): pass",
        "class result: pass",
        "import other as result",
        "from other import result",
        "if flag:\n    result = 1",
        "def nested():\n    global result\n    result = 1",
        "def nested():\n    nonlocal result",
        "try:\n    pass\nexcept Exception as result:\n    pass",
        "match data:\n    case result:\n        pass",
        "match data:\n    case [*result]:\n        pass",
        "match data:\n    case {**result}:\n        pass",
        'exec("result = 1")',
        'eval("1")',
        "globals()",
        "locals()",
        "vars()",
        "print(result)",
        "consume(result)",
        "other = metric(y, p)",
    ],
)
def test_ambiguous_binding_never_claims_call_result(fragment):
    source = (
        "from sklearn.metrics import roc_auc_score as metric\nresult = metric(y, p)\n"
        + fragment
    )
    assert binding(source) == ()


@pytest.mark.parametrize(
    "fragment",
    [
        "result = other(y, p)",
        "result = a = metric(y, p)",
        "result: float",
        "result = 1",
        'data["auc"] = metric(y, p)',
        "self.auc = metric(y, p)",
        "print(metric(y, p))",
        "if flag:\n    result = metric(y, p)",
        "def f():\n    return metric(y, p)",
        "match value:\n    case _: pass",
    ],
)
def test_non_direct_binding_is_not_automatic(fragment):
    assert (
        binding("from sklearn.metrics import roc_auc_score as metric\n" + fragment)
        == ()
    )
