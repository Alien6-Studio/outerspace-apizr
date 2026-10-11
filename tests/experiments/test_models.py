"""Strict boundaries for intended and observed scientific evidence."""

import json
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from apizr.experiments import (
    EnvironmentEvidence,
    EnvironmentValue,
    ExecutionIntent,
    ExperimentPlan,
    ExperimentRun,
    InputArtifact,
    Metric,
    OutputArtifact,
    PackageEvidence,
    Parameter,
    RandomnessControl,
    RunDiagnostic,
    RunTiming,
    SourceIdentity,
    plan_bytes,
    run_bytes,
    validate_run_binding,
)
from apizr.experiments import (
    EvidenceOrigin as Origin,
)


@pytest.mark.parametrize(
    "reference",
    [
        "/Users/alice/x",
        "C:\\Users\\alice",
        "C:/project/file",
        "../escape",
        "x/../escape",
        "./x",
        "a//b",
        "a/",
        "a\x00b",
        "a\nb",
        "a\x7fb",
        "https://host/x",
        "~user/x",
        "a\ud800",
    ],
)
def test_portable_references(reference):
    with pytest.raises(ValueError):
        SourceIdentity(kind="python", reference=reference, digest="a" * 64)
    with pytest.raises(ValueError):
        InputArtifact(name="data", reference=reference, origin=Origin.UNKNOWN)


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), -float("inf"), True, "0.9", None, 2**63]
)
def test_metric_finite_value_domain(value):
    if value is None or type(value) in (bool, str):
        metric = Metric(name="auc", value=value, origin=Origin.RUNTIME)
        assert metric.value == value and type(metric.value) is type(value)
    else:
        with pytest.raises(ValidationError):
            Metric(name="auc", value=value, origin=Origin.RUNTIME)


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        -float("inf"),
        {"nested": [float("nan")]},
        {1: "value"},
        {"x" * 257: None},
        "x" * 8193,
        "\ud800",
        {"\ud800": 1},
        [0] * 1025,
        {str(i): 0 for i in range(1025)},
        2**63,
        -(2**63) - 1,
        {1, 2},
        b"code",
        lambda: None,
        Path("file"),
        object(),
    ],
)
def test_parameter_rejects_non_json_or_unbounded(value):
    with pytest.raises(ValueError):
        Parameter(name="control", value=value, origin=Origin.DECLARED)


def test_json_depth_nodes_bytes_and_cycles():
    deep = 0
    for _ in range(17):
        deep = [deep]
    cycle = []
    cycle.append(cycle)
    for invalid in (deep, cycle, [[0] * 1024 for _ in range(4)], ["é" * 8192] * 5):
        with pytest.raises(ValueError, match="experiment_value_(complexity|byte_size)"):
            Parameter(name="control", value=invalid, origin=Origin.DECLARED)
    valid = 0
    for _ in range(16):
        valid = [valid]
    Parameter(name="control", value=valid, origin=Origin.DECLARED)


def test_json_values_are_copied_and_deeply_frozen(pair):
    caller = {"layers": [None, True, 7, 0.5, "café", {"weights": [1, 2]}]}
    parameter = Parameter(name="token_count", value=caller, origin=Origin.DECLARED)
    before = parameter.model_dump_json()
    caller["layers"][-1]["weights"][0] = 99
    assert parameter.model_dump_json() == before
    with pytest.raises(TypeError):
        parameter.value["extra"] = 1
    with pytest.raises(TypeError):
        parameter.value["layers"][-1]["weights"][0] = 99
    with pytest.raises(ValidationError, match="frozen_instance"):
        parameter.value = None
    plan, run = pair
    with pytest.raises(ValidationError, match="frozen_instance"):
        plan.subject.digest = "a" * 64
    with pytest.raises(ValidationError, match="frozen_instance"):
        run.status = "failed"
    assert "café" in parameter.model_dump_json()
    assert parameter.value["layers"][2] == 7


@pytest.mark.parametrize(
    "model,kwargs",
    [
        (InputArtifact, {"name": "x", "digest": "a" * 64}),
        (InputArtifact, {"name": "x", "size": 0}),
        (Parameter, {"name": "x", "value": 1}),
        (RandomnessControl, {"provider": "numpy", "name": "seed", "value": 1}),
        (EnvironmentValue, {"value": "CPython"}),
        (PackageEvidence, {"name": "numpy", "version": "2.0"}),
    ],
)
def test_unknown_evidence_never_claims_known_value(model, kwargs):
    with pytest.raises(ValidationError):
        model(origin=Origin.UNKNOWN, **kwargs)


@pytest.mark.parametrize("origin", [Origin.DECLARED, Origin.STATIC, Origin.RUNTIME])
def test_known_environment_requires_a_value(origin):
    for model, kwargs in (
        (EnvironmentValue, {"value": None}),
        (PackageEvidence, {"name": "numpy", "version": None}),
    ):
        with pytest.raises(ValidationError):
            model(origin=origin, **kwargs)


def test_partial_unknown_and_no_fake_observation():
    unknown = Origin.UNKNOWN
    subject = SourceIdentity(kind="python", reference="train.py", digest="a" * 64)
    plan = ExperimentPlan(
        subject=subject,
        execution=ExecutionIntent(kind="local-training"),
        inputs=(InputArtifact(name="data", origin=unknown),),
        parameters=(Parameter(name="batch_size", value=None, origin=unknown),),
        randomness=(
            RandomnessControl(
                provider="numpy", name="seed", value=None, origin=unknown
            ),
        ),
        environment=EnvironmentEvidence(
            packages=(PackageEvidence(name="numpy", version=None, origin=unknown),)
        ),
    )
    run = ExperimentRun(
        plan_digest=sha256(plan_bytes(plan)).hexdigest(),
        subject=subject,
        status="cancelled",
        observed_inputs=plan.inputs,
        effective_parameters=plan.parameters,
        randomness=plan.randomness,
        environment=plan.environment,
    )
    validate_run_binding(run, plan)
    assert plan.subject.capability_id is None
    assert run.metrics == run.outputs == ()
    assert run.timing is None
    assert b'"runtime"' not in run_bytes(run)


@pytest.mark.parametrize("field", ["inputs", "parameters", "randomness", "environment"])
def test_plan_rejects_runtime_observations(pair, field):
    data = pair[0].model_dump(mode="json")
    record = data[field][0] if field != "environment" else data[field]["python_version"]
    record["origin"] = "runtime"
    with pytest.raises(ValidationError, match="plan_contains_runtime"):
        ExperimentPlan.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("origin", ["declared", "static"])
@pytest.mark.parametrize(
    "field", ["observed_inputs", "effective_parameters", "randomness", "environment"]
)
def test_run_rejects_unobserved_evidence(pair, field, origin):
    data = pair[1].model_dump(mode="json")
    record = data[field][0] if field != "environment" else data[field]["python_version"]
    record["origin"] = origin
    with pytest.raises(ValidationError, match="run_contains_unobserved"):
        ExperimentRun.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("origin", [Origin.STATIC, Origin.RUNTIME, Origin.UNKNOWN])
def test_execution_controls_are_declared(origin):
    with pytest.raises(ValidationError, match="execution_control_not_declared"):
        ExecutionIntent(
            kind="notebook", controls=(Parameter(name="x", value=None, origin=origin),)
        )


@pytest.mark.parametrize(
    "collection",
    [
        "inputs",
        "parameters",
        "randomness",
        "execution.controls",
        "environment.packages",
        "environment.artifacts",
        "observed_inputs",
        "effective_parameters",
        "metrics",
        "outputs",
        "diagnostics",
    ],
)
def test_duplicate_logical_identities(pair, collection):
    model = (
        pair[1]
        if collection
        in {
            "observed_inputs",
            "effective_parameters",
            "metrics",
            "outputs",
            "diagnostics",
        }
        else pair[0]
    )
    data = model.model_dump(mode="json")
    target = data
    for part in collection.split("."):
        target = target[part]
    if collection == "diagnostics":
        data["status"] = "failed"
        target.append({"code": "execution_failed", "origin": "runtime"})
    target.append(target[0].copy())
    if collection == "environment.packages":
        target[-1]["name"] = "Scikit_Learn"
    with pytest.raises(ValidationError, match="duplicate_identity"):
        type(model).model_validate_json(json.dumps(data))


def test_same_seed_name_from_distinct_providers_and_sorted_inventory():
    controls = tuple(
        RandomnessControl(
            provider=provider, name="seed", value=1, origin=Origin.DECLARED
        )
        for provider in ("torch", "numpy")
    )
    plan = ExperimentPlan(
        subject=SourceIdentity(kind="python", reference="train.py", digest="a" * 64),
        execution=ExecutionIntent(kind="training"),
        randomness=controls,
    )
    assert [c.provider for c in plan.randomness] == ["numpy", "torch"]
    env = EnvironmentEvidence(
        packages=(
            PackageEvidence(name="Z_package", version="1", origin=Origin.STATIC),
            PackageEvidence(name="A.Package", version="2", origin=Origin.STATIC),
        )
    )
    assert [p.name for p in env.packages] == ["a-package", "z-package"]


def test_timing_normalizes_utc_and_partial_intervals():
    moment = datetime(2026, 1, 1, 2, tzinfo=timezone(timedelta(hours=2)))
    timing = RunTiming(started_at=moment, duration_seconds=0, origin=Origin.RUNTIME)
    assert timing.started_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert timing.model_dump(mode="json")["started_at"] == "2026-01-01T00:00:00Z"
    RunTiming(ended_at=moment, origin=Origin.RUNTIME)
    RunTiming(duration_seconds=0.1, origin=Origin.RUNTIME)
    with pytest.raises(ValidationError, match="timing_empty"):
        RunTiming(origin=Origin.RUNTIME)
    with pytest.raises(ValidationError, match="timing_reversed"):
        RunTiming(
            started_at=moment,
            ended_at=moment - timedelta(seconds=1),
            origin=Origin.RUNTIME,
        )
    with pytest.raises(ValidationError):
        RunTiming(started_at=datetime(2026, 1, 1), origin=Origin.RUNTIME)
    for value in (-1, float("nan"), float("inf"), -float("inf"), True):
        with pytest.raises(ValidationError):
            RunTiming(duration_seconds=value, origin=Origin.RUNTIME)


def test_failure_diagnostics_are_bounded_codes(pair):
    diagnostic = RunDiagnostic(code="execution_failed", origin=Origin.RUNTIME)
    run = pair[1]
    for status in ("failed", "cancelled"):
        updated = run.model_copy(
            update={"status": status, "diagnostics": (diagnostic,)}
        )
        assert run_bytes(updated)
    with pytest.raises(ValidationError, match="success_has_failure"):
        run_bytes(run.model_copy(update={"diagnostics": (diagnostic,)}))
    for code in ("Traceback\nfile", "x" * 129, "", "Runtime Error"):
        with pytest.raises(ValidationError):
            RunDiagnostic(code=code, origin=Origin.RUNTIME)


@pytest.mark.parametrize(
    "which,update",
    [
        (0, {"schema_version": "apizr.experiment-plan/v2"}),
        (0, {"uuid": "random"}),
        (0, {"created_at": "now"}),
        (0, {"reproducible": True}),
        (1, {"status": "running"}),
        (1, {"schema_version": "apizr.experiment-run/v2"}),
        (1, {"plan_digest": "bad"}),
        (1, {"root_cause": "seed"}),
    ],
)
def test_unchecked_models_cannot_bypass_validation(pair, which, update):
    model = pair[which]
    encoder = (plan_bytes, run_bytes)[which]
    with pytest.raises(ValidationError):
        encoder(model.model_copy(update=update))
    if len(set(update) - type(model).model_fields.keys()) == 0:
        with pytest.raises(ValidationError):
            encoder(type(model).model_construct(**{**dict(model), **update}))
    with pytest.raises(ValidationError):
        type(model).model_validate_json(
            json.dumps({**model.model_dump(mode="json"), **update})
        )


def test_unchecked_nested_models_are_revalidated(pair):
    plan, run = pair
    bad_subject = plan.subject.model_copy(update={"reference": "/tmp/source"})
    bad_metric = Metric.model_construct(
        name="auc", value=float("nan"), origin=Origin.RUNTIME
    )
    naive = RunTiming.model_construct(
        started_at=datetime(2026, 1, 1), origin=Origin.RUNTIME
    )
    for encoder, model in (
        (plan_bytes, plan.model_copy(update={"subject": bad_subject})),
        (
            plan_bytes,
            plan.model_copy(
                update={
                    "parameters": (
                        Parameter.model_construct(
                            name="x", value={"x": float("inf")}, origin=Origin.DECLARED
                        ),
                    )
                }
            ),
        ),
        (run_bytes, run.model_copy(update={"metrics": (bad_metric,)})),
        (run_bytes, run.model_copy(update={"metrics": run.metrics * 2})),
        (run_bytes, run.model_copy(update={"timing": naive})),
        (
            run_bytes,
            run.model_copy(
                update={"outputs": (run.outputs[0].model_copy(update={"secret": "x"}),)}
            ),
        ),
    ):
        with pytest.raises(ValidationError):
            encoder(model)
    with pytest.raises(ValidationError):
        validate_run_binding(run, plan.model_copy(update={"subject": bad_subject}))
    with pytest.raises(ValidationError):
        validate_run_binding(run.model_copy(update={"timing": naive}), plan)


@pytest.mark.parametrize(
    "model,kwargs",
    [
        (SourceIdentity, {"kind": "python", "reference": "a.py", "digest": "A" * 64}),
        (
            SourceIdentity,
            {
                "kind": "python",
                "reference": "a.py",
                "digest": "a" * 64,
                "module": "not-valid",
            },
        ),
        (InputArtifact, {"name": "data", "size": -1, "origin": Origin.STATIC}),
        (Parameter, {"name": "x" * 129, "value": 1, "origin": Origin.DECLARED}),
        (Parameter, {"name": "bad\nname", "value": 1, "origin": Origin.DECLARED}),
        (
            PackageEvidence,
            {"name": "bad name", "version": "1", "origin": Origin.STATIC},
        ),
        (
            Metric,
            {"name": "auc", "value": 0.9, "unit": "x" * 65, "origin": Origin.RUNTIME},
        ),
        (
            OutputArtifact,
            {
                "name": "model",
                "digest": "a" * 64,
                "media_type": "x" * 129,
                "origin": Origin.RUNTIME,
            },
        ),
    ],
)
def test_string_numeric_and_identity_bounds(model, kwargs):
    with pytest.raises(ValidationError):
        model(**kwargs)


@pytest.mark.parametrize(
    "which,path,limit",
    [
        (0, "inputs", 256),
        (0, "parameters", 256),
        (0, "randomness", 128),
        (0, "environment.packages", 4096),
        (0, "environment.artifacts", 64),
        (0, "execution.controls", 128),
        (1, "observed_inputs", 256),
        (1, "effective_parameters", 256),
        (1, "randomness", 128),
        (1, "metrics", 256),
        (1, "outputs", 256),
        (1, "diagnostics", 32),
    ],
)
def test_collection_bounds(pair, which, path, limit):
    data = pair[which].model_dump(mode="json")
    target = data
    for part in path.split(".")[:-1]:
        target = target[part]
    field = path.split(".")[-1]
    sample = (
        target[field][0]
        if field != "diagnostics"
        else {"code": "failed", "origin": "runtime"}
    )
    target[field] = [sample] * (limit + 1)
    with pytest.raises(ValidationError, match="too_long"):
        type(pair[which]).model_validate_json(json.dumps(data))


def test_total_artifact_byte_bound(pair):
    # Individually valid values cannot produce an unbounded canonical artifact.
    plan = pair[0].model_copy(
        update={
            "parameters": tuple(
                Parameter(name=f"p{i}", value=["x" * 8192] * 7, origin=Origin.DECLARED)
                for i in range(75)
            )
        }
    )
    with pytest.raises(ValueError, match="frame_size"):
        plan_bytes(plan)


def test_minimal_run_and_opaque_capability_identity():
    subject = SourceIdentity(
        kind="python",
        reference="train.py",
        digest="a" * 64,
        module="módulo",
        capability_id="python:módulo:predict",
    )
    plan = ExperimentPlan(subject=subject, execution=ExecutionIntent(kind="training"))
    run = ExperimentRun(
        subject=subject,
        plan_digest=sha256(plan_bytes(plan)).hexdigest(),
        status="success",
    )
    validate_run_binding(run, plan)
    assert run_bytes(run)
    assert "módulo".encode() in plan_bytes(plan)


@pytest.mark.parametrize("origin", [Origin.DECLARED, Origin.STATIC, Origin.UNKNOWN])
@pytest.mark.parametrize(
    "model,kwargs",
    [
        (Metric, {"name": "score", "value": 1.0}),
        (OutputArtifact, {"name": "model", "digest": "a" * 64}),
        (RunDiagnostic, {"code": "failed"}),
        (RunTiming, {"duration_seconds": 1.0}),
    ],
)
def test_runtime_records_require_runtime_origin(origin, model, kwargs):
    with pytest.raises(ValidationError):
        model(origin=origin, **kwargs)


def test_all_nested_contracts_reject_unknown_fields(pair):
    def reject_extra(model):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            type(model).model_validate(
                model.model_copy(update={"credential": "forbidden"})
            )
        for value in dict(model).values():
            if hasattr(type(value), "model_fields"):
                reject_extra(value)
            elif isinstance(value, tuple):
                for child in value:
                    reject_extra(child)

    for artifact in pair:
        reject_extra(artifact)
    reject_extra(RunDiagnostic(code="failed", origin=Origin.RUNTIME))


@pytest.mark.parametrize(
    "capability",
    ["python:module:bad name", "x\x00y", "x\ud800y", "x/y", "x\\y", "x" * 513],
)
def test_capability_is_a_bounded_logical_identity(capability):
    with pytest.raises(ValueError):
        SourceIdentity(
            kind="python",
            reference="train.py",
            digest="a" * 64,
            capability_id=capability,
        )
