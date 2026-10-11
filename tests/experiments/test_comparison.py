"""Directional evidence semantics, strict contract, bounded canonical comparison."""

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

from apizr.experiments import (
    EnvironmentEvidence,
    EnvironmentValue,
    EvidenceOrigin,
    InputArtifact,
    Metric,
    PackageEvidence,
    Parameter,
    RandomnessControl,
    RunTiming,
)
from apizr.experiments import comparison as core
from apizr.experiments.comparison import ChangeState as S
from apizr.experiments.comparison import ExperimentDiff, compare_runs, diff_bytes
from apizr.experiments.comparison_reporting import diff_text

from .comparison_support import record, replace

R, U, D = EvidenceOrigin.RUNTIME, EvidenceOrigin.UNKNOWN, EvidenceOrigin.DECLARED


def test_self_preserves_unknown_and_exact_ids():
    a = record()
    diff = compare_runs(a, a)
    assert diff.source.state == diff.plan_state == diff.status.state == S.SAME
    assert diff.serving == S.UNKNOWN
    assert diff.source.capability_id == S.UNKNOWN
    assert diff.data[0].content_state == S.SAME
    assert diff.data[1].content_state == S.UNKNOWN
    assert diff.metrics[0].delta == 0
    assert (
        diff.material_counts.changed
        == diff.material_counts.added
        == diff.material_counts.removed
        == 0
    )
    assert diff.material_counts.unknown > 0
    assert diff.result_counts.unknown == diff.result_counts.changed == 0
    assert diff.run_a_digest == diff.run_b_digest == a.run_digest
    assert diff.plan_a_digest == diff.plan_b_digest == a.plan_digest
    assert "No material recorded differences among comparable evidence." in diff_text(
        diff
    )


@pytest.mark.parametrize("side", ["a", "b"])
@pytest.mark.parametrize(
    "forgery", ["run_digest", "plan_digest", "run", "plan", "binding"]
)
def test_revalidates_records_and_nested_binding(side, forgery):
    a = record()
    if forgery in {"run_digest", "plan_digest"}:
        bad = a.model_copy(update={forgery: "a" * 64})
    elif forgery == "run":
        bad = a.model_copy(
            update={"run": a.run.model_copy(update={"status": "failed"})}
        )
    elif forgery == "plan":
        bad = a.model_copy(
            update={"plan": a.plan.model_copy(update={"parameters": ()})}
        )
    else:
        bad = a.model_copy(
            update={"run": a.run.model_copy(update={"plan_digest": "b" * 64})}
        )
    with pytest.raises(ValueError):
        compare_runs(bad if side == "a" else a, bad if side == "b" else a)


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "python"),
        ("reference", "train.py"),
        ("digest", "a" * 64),
        ("executable_digest", "b" * 64),
        ("module", "train"),
        ("capability_id", "python:train:predict"),
    ],
)
def test_source_exact_fields(field, value):
    a = record()
    b = record(plan=replace(a.plan, subject=replace(a.plan.subject, **{field: value})))
    result = compare_runs(a, b)
    assert result.source.state == result.plan_state == S.CHANGED
    assert getattr(result.source, field) == (
        S.ADDED if field == "capability_id" else S.CHANGED
    )
    assert result.metrics[0].state == S.SAME


@pytest.mark.parametrize(
    "left,right,state",
    [
        (None, None, S.UNKNOWN),
        (None, "a", S.ADDED),
        ("a", None, S.REMOVED),
        ("a", "a", S.SAME),
        ("a", "b", S.CHANGED),
    ],
)
def test_serving(left, right, state):
    base = record()
    records = [
        record(
            plan=replace(
                base.plan,
                subject=replace(
                    base.plan.subject,
                    capability_id=x,
                    executable_digest=None,
                    module=None,
                ),
            )
        )
        for x in (left, right)
    ]
    result = compare_runs(*records)
    assert result.serving == state
    assert result.source.executable_digest == result.source.module == S.UNKNOWN


def test_dataset_only_change_and_missing_observation():
    a = record()
    data = replace(a.run.observed_inputs[0], digest="b" * 64)
    b = record(observed_inputs=(data,))
    result = compare_runs(a, b)
    assert result.source.state == result.plan_state == S.SAME
    assert result.data[0].content_state == S.CHANGED
    assert result.data[0].selection_state == S.SAME
    assert all(p.planned_state == p.observed_state == S.SAME for p in result.parameters)
    assert result.observed_environment == compare_runs(a, a).observed_environment
    absent = record(observed_inputs=())
    assert compare_runs(a, absent).data[0].content_state == S.UNKNOWN
    assert compare_runs(absent, absent).data[0].content_state == S.UNKNOWN


def test_remote_reference_and_selection_membership():
    a = record()
    remote = InputArtifact(
        name="remote", uri="s3://bucket/train.csv", origin=D, content_origin=U
    )
    b = record(plan=replace(a.plan, inputs=(remote,)), observed_inputs=())
    same = compare_runs(b, b).data[0]
    assert same.reference_state == same.selection_state == S.SAME
    assert same.content_state == S.UNKNOWN
    result = compare_runs(a, b)
    assert [i.name for i in result.data] == ["remote", "train", "validation"]
    assert [i.selection_state for i in result.data] == [S.ADDED, S.REMOVED, S.REMOVED]
    # Runtime-only names never acquire invented Plan intent or a reference.
    c = record(plan=replace(a.plan, inputs=()), observed_inputs=a.run.observed_inputs)
    item = compare_runs(c, c).data[0]
    assert item.reference_state == item.selection_state == S.UNKNOWN
    assert item.content_state == S.SAME


@pytest.mark.parametrize(
    "left,right,expected",
    [
        (8, 12, S.CHANGED),
        (None, None, S.SAME),
        (1, 1.0, S.CHANGED),
        (True, 1, S.CHANGED),
        ({"a": 1, "b": [2]}, {"b": [2], "a": 1}, S.SAME),
        ([1, 2], [2, 1], S.CHANGED),
    ],
)
def test_parameter_intended_observed_null_and_canonical_values(left, right, expected):
    a = record()
    pair = [
        record(
            plan=replace(
                a.plan, parameters=(Parameter(name="depth", value=v, origin=D),)
            ),
            effective_parameters=(Parameter(name="depth", value=v, origin=R),),
        )
        for v in (left, right)
    ]
    p = compare_runs(*pair).parameters[0]
    assert p.planned_state == p.observed_state == expected
    assert p.observed_membership == S.SAME
    absent = record(plan=pair[1].plan, effective_parameters=())
    missing = compare_runs(pair[0], absent).parameters[0]
    assert missing.planned_state == expected
    assert missing.observed_state == S.UNKNOWN
    assert missing.observed_membership == S.REMOVED


def test_parameter_unknown_and_membership():
    a = record()
    unknown = Parameter(name="p", value=None, origin=U)
    both = record(
        plan=replace(a.plan, parameters=(unknown,)), effective_parameters=(unknown,)
    )
    diff = compare_runs(both, both)
    assert (
        diff.parameters[0].planned_state
        == diff.parameters[0].observed_state
        == S.UNKNOWN
    )
    empty = record(plan=replace(a.plan, parameters=()), effective_parameters=())
    assert compare_runs(empty, both).parameters[0].planned_state == S.ADDED
    assert compare_runs(both, empty).parameters[0].planned_state == S.REMOVED


def test_randomness_independent_origins_and_composite_keys():
    a = record()
    static = RandomnessControl(provider="numpy", name="seed", value=42, origin=D)
    unknown = RandomnessControl(
        provider="torch", name="accelerator_determinism", value=None, origin=U
    )
    a = record(plan=replace(a.plan, randomness=(static, unknown)), randomness=())
    b = record(
        plan=replace(a.plan, randomness=(replace(static, value=43), unknown)),
        randomness=(),
    )
    result = compare_runs(a, b)
    assert result.randomness[0].planned_state == S.CHANGED
    assert result.randomness[0].observed_state == S.UNKNOWN
    assert result.randomness[1].planned_state == S.UNKNOWN
    c = record(
        plan=replace(
            a.plan, randomness=(replace(static, value=None, origin=U), unknown)
        ),
        randomness=(),
    )
    assert compare_runs(a, c).randomness[0].planned_state == S.UNKNOWN
    runtime = replace(static, origin=R)
    d = record(plan=a.plan, randomness=(runtime, replace(runtime, provider="stdlib")))
    assert all(
        r.observed_state == S.ADDED
        for r in compare_runs(a, d).randomness
        if r.name == "seed"
    )


def test_environment_package_only_and_unknown_facts():
    a = record()
    environment = a.run.environment
    b = record(
        environment=replace(
            environment, packages=(replace(environment.packages[0], version="1.8.1"),)
        )
    )
    result = compare_runs(a, b)
    assert result.observed_environment.packages[0].state == S.CHANGED
    assert result.planned_environment.packages[0].state == S.SAME
    assert (
        result.source.state
        == result.plan_state
        == result.data[0].content_state
        == S.SAME
    )
    unknown = EnvironmentEvidence(
        python_version=EnvironmentValue(value=None, origin=U),
        packages=(PackageEvidence(name="torch", version=None, origin=U),),
        artifacts=(InputArtifact(name="lock", reference="uv.lock", origin=U),),
    )
    c = record(environment=unknown)
    view = compare_runs(c, c).observed_environment
    assert (
        view.python_version.state
        == view.packages[0].state
        == view.artifacts[0].state
        == S.UNKNOWN
    )
    absent = record(environment=None)
    assert compare_runs(absent, c).observed_environment.packages[0].state == S.ADDED
    assert compare_runs(c, absent).observed_environment.artifacts[0].state == S.REMOVED
    changed = record(
        environment=replace(
            environment,
            artifacts=(replace(environment.artifacts[0], reference="other.lock"),),
            platform=EnvironmentValue(value="darwin", origin=R),
        )
    )
    view = compare_runs(a, changed).observed_environment
    assert view.artifacts[0].state == view.platform.state == S.CHANGED


@pytest.mark.parametrize(
    "left,right,ua,ub,state,delta",
    [
        (0.941, 0.948, None, None, S.CHANGED, 0.948 - 0.941),
        (1, 1.0, None, None, S.CHANGED, 0.0),
        (True, False, None, None, S.CHANGED, None),
        (True, 1, None, None, S.CHANGED, None),
        (1, True, None, None, S.CHANGED, None),
        ("1", "2", None, None, S.CHANGED, None),
        (None, None, None, None, S.SAME, None),
        (
            {"precision": 0.87, "recall": 0.82},
            {"precision": 0.88, "recall": 0.82},
            None,
            None,
            S.CHANGED,
            None,
        ),
        ([1, 2], [2, 1], None, None, S.CHANGED, None),
        (5, 0.005, "ms", "s", S.CHANGED, None),
        (-1e308, 1e308, None, None, S.CHANGED, None),
        (-(2**63), 2**63 - 1, "units", "units", S.CHANGED, 2**64 - 1),
    ],
)
def test_metric_rules(left, right, ua, ub, state, delta):
    a, b = [
        record(metrics=(Metric(name="score", value=v, unit=u, origin=R),))
        for v, u in ((left, ua), (right, ub))
    ]
    result = compare_runs(a, b)
    item = result.metrics[0]
    assert result.plan_state == S.SAME
    assert item.state == state and item.delta == delta
    payload = json.loads(diff_bytes(result))["metrics"][0]
    assert ("delta" in payload) == (delta is not None)
    assert payload["a"]["value"] == left and payload["b"]["value"] == right


def test_output_full_evidence_and_membership():
    a = record()
    for field, value in [
        ("digest", "c" * 64),
        ("reference", "model.bin"),
        ("size", 2048),
        ("media_type", "application/json"),
    ]:
        b = record(outputs=(replace(a.run.outputs[0], **{field: value}),))
        output = compare_runs(a, b).outputs[0]
        assert output.state == S.CHANGED
        assert output.content_state == (S.CHANGED if field == "digest" else S.SAME)
    empty = record(outputs=(), metrics=(), status="failed")
    result = compare_runs(a, empty)
    assert result.outputs[0].state == result.metrics[0].state == S.REMOVED
    assert result.outputs[0].content_state == S.UNKNOWN
    assert result.status.state == S.CHANGED
    reverse = compare_runs(record(status="cancelled", outputs=(), metrics=()), a)
    assert reverse.outputs[0].state == reverse.metrics[0].state == S.ADDED
    assert reverse.status.a == "cancelled"


def test_timing_is_not_counted():
    a = record()
    b = record(timing=RunTiming(duration_seconds=123.0, origin=R))
    result = compare_runs(a, b)
    same = compare_runs(a, a)
    assert a.run_digest != b.run_digest
    assert result.material_counts == same.material_counts
    assert result.result_counts == same.result_counts
    assert "No material recorded differences among comparable evidence." in diff_text(
        result
    )
    assert "duration_seconds" not in diff_bytes(result).decode()


def test_strict_immutable_schema_and_bounds(monkeypatch):
    result = compare_runs(record(), record())
    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "docs/specs/apizr-experiment-diff-v1.schema.json"
        ).read_bytes()
    )
    assert schema == ExperimentDiff.model_json_schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result.model_dump(mode="json"))
    assert ExperimentDiff.model_validate_json(diff_bytes(result)) == result
    with pytest.raises(ValueError):
        result.serving = S.SAME
    with pytest.raises(ValueError):
        ExperimentDiff.model_validate(result.model_dump() | {"causes": []})
    with pytest.raises(ValueError):
        ExperimentDiff.model_validate(
            result.model_dump() | {"outputs": result.outputs * 513}
        )
    with pytest.raises(ValueError):
        replace(result.metrics[0], delta=float("inf"))
    monkeypatch.setattr(core, "MAX_DIFF_BYTES", len(diff_bytes(result)) - 1)
    with pytest.raises(ValueError):
        compare_runs(record(), record())
    monkeypatch.setattr(core, "MAX_DIFF_BYTES", 10)
    with pytest.raises(ValueError):
        compare_runs(record(), record())


def test_reviewed_fixed_records_bytes_and_text():
    from apizr.experiments.store import RunRecord

    root = Path(__file__).resolve().parents[1] / "fixtures/experiments/comparison/v1"
    a, b = [
        RunRecord.model_validate_json((root / f"{side}.record.json").read_bytes())
        for side in ("a", "b")
    ]
    result = compare_runs(a, b)
    assert diff_bytes(result) == (root / "diff.json").read_bytes()
    assert diff_text(result).encode() == (root / "diff.txt").read_bytes()


def swap(value):
    if isinstance(value, str) and value in {s.value for s in S}:
        return {S.ADDED: S.REMOVED, S.REMOVED: S.ADDED}.get(value, value)
    if isinstance(value, dict):
        keys = {
            "a": "b",
            "b": "a",
            "planned_a": "planned_b",
            "planned_b": "planned_a",
            "observed_a": "observed_b",
            "observed_b": "observed_a",
            "run_a_digest": "run_b_digest",
            "run_b_digest": "run_a_digest",
            "plan_a_digest": "plan_b_digest",
            "plan_b_digest": "plan_a_digest",
            "added": "removed",
            "removed": "added",
        }
        return {
            keys.get(k, k): (-v if k == "delta" and v is not None else swap(v))
            for k, v in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [swap(v) for v in value]
    return value


@st.composite
def records(draw):
    base = record()
    value = draw(
        st.one_of(
            st.none(),
            st.booleans(),
            st.integers(-1000, 1000),
            st.floats(allow_nan=False, allow_infinity=False),
            st.dictionaries(st.sampled_from(["x", "y"]), st.integers(-10, 10)),
        )
    )
    present = draw(st.lists(st.booleans(), min_size=8, max_size=8))
    unknown = draw(st.booleans())
    parameter = Parameter(
        name="depth", value=None if unknown else value, origin=U if unknown else D
    )
    randomness = RandomnessControl(
        provider="numpy", name="seed", value=parameter.value, origin=parameter.origin
    )
    plan = replace(
        base.plan,
        inputs=base.plan.inputs if present[0] else (),
        parameters=(parameter,) if present[1] else (),
        randomness=(randomness,) if present[2] else (),
        environment=base.plan.environment if present[3] else None,
        subject=replace(
            base.plan.subject,
            capability_id="python:train:predict" if present[4] else None,
        ),
    )
    return record(
        plan=plan,
        observed_inputs=base.run.observed_inputs if present[5] else (),
        effective_parameters=(replace(parameter, origin=U if unknown else R),)
        if present[6]
        else (),
        randomness=(replace(randomness, origin=U if unknown else R),)
        if present[7]
        else (),
        environment=base.run.environment if present[2] else None,
        metrics=(Metric(name="score", value=value, origin=R),) if present[3] else (),
        outputs=base.run.outputs if present[4] else (),
        status=draw(st.sampled_from(["success", "failed", "cancelled"])),
    )


@settings(max_examples=60, deadline=None)
@given(records(), records())
def test_swap_every_category(a, b):
    assert swap(compare_runs(a, b).model_dump(mode="json")) == compare_runs(
        b, a
    ).model_dump(mode="json")


@settings(max_examples=30, deadline=None)
@given(records())
def test_self_property(a):
    result = compare_runs(a, a)
    for counts in (result.material_counts, result.result_counts):
        assert counts.changed == counts.added == counts.removed == 0
    for metric in result.metrics:
        assert metric.state == S.SAME
        assert metric.delta is None or metric.delta == 0


@given(
    st.floats(allow_nan=False, allow_infinity=False),
    st.floats(allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50, deadline=None)
def test_finite_delta_swap(a, b):
    left = record(metrics=(Metric(name="score", value=a, origin=R),))
    right = record(metrics=(Metric(name="score", value=b, origin=R),))
    ab, ba = compare_runs(left, right).metrics[0], compare_runs(right, left).metrics[0]
    assert (ab.delta is None) == (ba.delta is None)
    if ab.delta is not None:
        assert ab.delta == -ba.delta
