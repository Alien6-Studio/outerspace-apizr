"""Explicit observations bind to a Plan; static signals never supply their values."""

import json
import re
from hashlib import sha256
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.experiments import (
    EvidenceOrigin as O,
)
from apizr.experiments import (
    ExecutionIntent,
    ExperimentPlan,
    ExperimentRun,
    Metric,
    OutputArtifact,
    OutputDeclaration,
    SourceIdentity,
    capture_metric,
    discover_metrics,
    discover_outputs,
    fingerprint_output,
    plan_bytes,
    plan_digest,
    run_bytes,
    run_digest,
    validate_run_binding,
)

from .conftest import example_pair
from .test_properties import values

FIXTURE = Path(__file__).parents[1] / "fixtures/experiments/results/train.py"


def test_realistic_source_and_separate_explicit_observations(tmp_path):
    source = FIXTURE.read_bytes()
    metric_signals = discover_metrics(source, source_reference="train.py")
    output_signals = discover_outputs(source, source_reference="train.py")
    assert [s.name for s in metric_signals.signals] == [
        "roc_auc",
        "precision",
        "recall",
    ]
    assert len(output_signals.signals) == 1
    assert not metric_signals.diagnostics and not output_signals.diagnostics
    plan = ExperimentPlan(
        subject=SourceIdentity(
            kind="python", reference="train.py", digest=sha256(source).hexdigest()
        ),
        execution=ExecutionIntent(kind="training"),
    )
    original_plan = plan_bytes(plan)
    # Explicit fixture values, not claimed to have been computed by sklearn.
    observed = tuple(
        capture_metric(name, value)
        for name, value in (
            ("roc_auc", 0.91),
            ("precision", 0.87),
            ("recall", 0.82),
            ("classification", {"precision": 0.87, "recall": 0.82}),
        )
    )
    (tmp_path / "artifacts").mkdir()
    path = tmp_path / "artifacts/model.joblib"
    path.write_bytes(b"opaque fixture model bytes; not a serialized estimator")
    selection = OutputDeclaration(
        name="model", reference=output_signals.signals[0].declaration.reference
    )

    def observed_run(metrics=observed):
        artifacts = fingerprint_output(tmp_path, selection).artifacts
        run = ExperimentRun(
            plan_digest=plan_digest(plan),
            subject=plan.subject,
            status="success",
            metrics=metrics,
            outputs=artifacts,
        )
        validate_run_binding(run, plan)
        return run

    a = observed_run()
    b = observed_run((capture_metric("roc_auc", 0.92), *observed[1:]))
    c = observed_run(
        (
            *observed[:3],
            capture_metric("classification", {"precision": 0.88, "recall": 0.82}),
        )
    )
    path.write_bytes(b"only the output bytes change")
    d = observed_run()
    assert len({run_digest(r) for r in (a, b, c, d)}) == 4
    assert len({r.plan_digest for r in (a, b, c, d)}) == 1
    assert plan_bytes(plan) == original_plan
    assert a.outputs == b.outputs == c.outputs
    assert a.metrics == d.metrics
    assert a.outputs[0].name == d.outputs[0].name == "model"
    assert a.outputs[0].reference == d.outputs[0].reference == "artifacts/model.joblib"
    assert a.outputs[0].digest != d.outputs[0].digest
    raw = run_bytes(a)
    restored = ExperimentRun.model_validate_json(raw)
    assert run_bytes(restored) == raw
    assert json.loads(raw)["metrics"][0]["value"] == {"precision": 0.87, "recall": 0.82}
    assert str(tmp_path).encode() not in raw


def test_metric_and_output_order_names_and_structured_canonicality():
    plan, run = example_pair()
    metrics = (
        capture_metric("z", [0.91, 0.89]),
        capture_metric("a", {"recall": 0.82, "precision": 0.87}),
    )
    a = run.model_copy(update={"metrics": metrics})
    b = run.model_copy(
        update={
            "metrics": (
                capture_metric("a", {"precision": 0.87, "recall": 0.82}),
                metrics[0],
            )
        }
    )
    assert run_bytes(a) == run_bytes(b)
    assert run_digest(a) != run_digest(
        run.model_copy(
            update={"metrics": (capture_metric("z", [0.89, 0.91]), metrics[1])}
        )
    )
    outputs = (
        OutputArtifact(
            name="z", reference="model.bin", digest="a" * 64, origin=O.RUNTIME
        ),
        OutputArtifact(
            name="a", reference="model.bin", digest="a" * 64, origin=O.RUNTIME
        ),
    )
    assert run_bytes(run.model_copy(update={"outputs": outputs})) == run_bytes(
        run.model_copy(update={"outputs": outputs[::-1]})
    )
    for field, items in (("metrics", metrics), ("outputs", outputs)):
        with pytest.raises(ValueError, match="duplicate_identity"):
            run_bytes(run.model_copy(update={field: (items[0],) * 2}))
    assert plan_digest(plan) == run.plan_digest


def test_unchecked_nested_evidence_revalidated():
    _, run = example_pair()
    for metric in (
        Metric.model_construct(name="x", value=float("nan"), origin=O.RUNTIME),
        capture_metric("x", 1).model_copy(update={"value": {"nested": [float("inf")]}}),
        capture_metric("x", 1).model_copy(
            update={"value": {"nested": 1}, "unit": "ms"}
        ),
        capture_metric("x", 1).model_copy(update={"origin": O.STATIC}),
    ):
        with pytest.raises(ValueError):
            run_bytes(run.model_copy(update={"metrics": (metric,)}))
    for artifact in (
        OutputArtifact.model_construct(
            name="model", digest="a" * 64, reference="/private/model", origin=O.RUNTIME
        ),
        run.outputs[0].model_copy(update={"reference": "../secret"}),
        run.outputs[0].model_copy(update={"origin": O.STATIC}),
    ):
        with pytest.raises(ValueError):
            run_bytes(run.model_copy(update={"outputs": (artifact,)}))
    signal = discover_metrics(
        "from sklearn.metrics import roc_auc_score\nroc_auc_score(y,p)",
        source_reference="train.py",
    ).signals[0]
    output = discover_outputs(
        'import joblib\njoblib.dump(model,"model.joblib")', source_reference="train.py"
    ).signals[0]
    for field, item in (
        ("metrics", signal),
        ("outputs", output),
        ("outputs", output.declaration),
    ):
        with pytest.raises(ValueError):
            run_bytes(run.model_copy(update={field: (item,)}))


@given(values)
@settings(max_examples=50, deadline=None)
def test_finite_json_metric_roundtrip(value):
    plan, run = example_pair()
    observed = run.model_copy(update={"metrics": (capture_metric("result", value),)})
    raw = run_bytes(observed)
    assert json.loads(raw)["metrics"][0]["value"] == value
    assert run_bytes(ExperimentRun.model_validate_json(raw)) == raw
    validate_run_binding(observed, plan)


@given(
    st.dictionaries(
        st.text(alphabet="abcde", min_size=1, max_size=5),
        st.integers(-1000, 1000),
        max_size=10,
    )
)
@settings(max_examples=30, deadline=None)
def test_metric_order_and_mapping_order_property(value):
    _, run = example_pair()
    a = capture_metric("a", value)
    b = capture_metric("b", 42)
    first = run.model_copy(update={"metrics": (a, b)})
    reversed_value = dict(reversed(list(value.items())))
    second = run.model_copy(
        update={"metrics": (b, capture_metric("a", reversed_value))}
    )
    assert run_bytes(first) == run_bytes(second)


def test_historical_numeric_and_output_json_unchanged():
    assert (
        capture_metric("roc_auc", 0.91).model_dump_json()
        == '{"name":"roc_auc","value":0.91,"unit":null,"origin":"runtime"}'
    )
    artifact = OutputArtifact(name="model", digest="a" * 64, origin=O.RUNTIME)
    assert "reference" not in artifact.model_dump_json()
    assert OutputArtifact.model_validate_json(artifact.model_dump_json()) == artifact


@pytest.mark.parametrize(
    "marker",
    ["metric-example", "results-discovery-example", "output-capture-example"],
)
def test_documented_examples_execute(marker):
    guide = Path(__file__).parents[2] / "docs/guides/experiment-results.md"
    match = re.search(
        rf"<!-- executable-{marker} -->\s*```python\n(.*?)\n```",
        guide.read_text(),
        re.DOTALL,
    )
    assert match is not None
    exec(compile(match.group(1), str(guide), "exec"), {})
