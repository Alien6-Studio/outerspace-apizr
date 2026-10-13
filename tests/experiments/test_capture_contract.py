"""v2 identities and unknowns, bounded values, canonical bytes and v1 reading."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from apizr.experiments import (
    CallParameter,
    CaptureIdentity,
    CaptureMode,
    CellIdentity,
    EnvironmentEvidence,
    EnvironmentValue,
    EvidenceOrigin,
    ExecutionIntent,
    ExperimentPlanV2,
    ExperimentRunV2,
    FunctionBinding,
    InputArtifact,
    RandomnessControl,
    RunDiagnostic,
    SourceEvidence,
    SourceIdentity,
    plan_bytes,
    plan_digest,
    read_plan,
    read_run,
    run_bytes,
    run_digest,
    validate_run_binding,
)
from apizr.experiments.comparison import compare_runs, diff_bytes
from apizr.experiments.history import history_bytes, list_runs, show_run

ROOT = Path(__file__).resolve().parents[2]


def pair(mode=CaptureMode.SDK_SESSION):
    capture = CaptureIdentity(
        mode=mode,
        producer="apizr.tracking",
        producer_version="1",
        function=FunctionBinding(
            module="train",
            qualified_name="fit",
            definition_id="b" * 32,
            origin=EvidenceOrigin.RUNTIME,
        ),
        cell=CellIdentity(execution_count=1, origin=EvidenceOrigin.RUNTIME),
        selected_parameters=("learning_rate",),
    )
    plan = ExperimentPlanV2(
        subject=SourceEvidence(),
        execution=ExecutionIntent(kind="in_process"),
        capture=capture,
    )
    run = ExperimentRunV2(
        plan_digest=plan_digest(plan),
        subject=plan.subject,
        capture=capture,
        execution_id="a" * 32,
        status="success",
        call_parameters=(
            CallParameter(
                name="learning_rate", value=0.1, origin=EvidenceOrigin.RUNTIME
            ),
        ),
    )
    return plan, run


@pytest.mark.parametrize("mode", list(CaptureMode))
def test_modes_roundtrip_through_canonical_versioned_readers(mode):
    plan, run = pair(mode)
    assert read_plan(plan_bytes(plan)) == plan
    assert read_run(run_bytes(run)) == run
    validate_run_binding(run, plan)
    assert len(run_digest(run)) == 64
    assert run_digest(run) != run.execution_id
    assert plan.subject.identity is None
    assert plan.subject.origin == EvidenceOrigin.UNKNOWN


@pytest.mark.parametrize(
    "name,model,encode",
    [("plan", ExperimentPlanV2, plan_bytes), ("run", ExperimentRunV2, run_bytes)],
)
def test_v2_schema_parity(name, model, encode):
    plan, run = pair()
    value = plan if name == "plan" else run
    schema = json.loads(
        (ROOT / f"docs/specs/apizr-experiment-{name}-v2.schema.json").read_bytes()
    )
    assert schema == model.model_json_schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(json.loads(encode(value)))


@pytest.mark.parametrize(
    "model,fields",
    [
        (SourceEvidence, {"origin": EvidenceOrigin.RUNTIME}),
        (FunctionBinding, {"module": "train"}),
        (FunctionBinding, {"origin": EvidenceOrigin.RUNTIME, "module": "train"}),
        (CellIdentity, {"execution_count": 1}),
        (CellIdentity, {"origin": EvidenceOrigin.RUNTIME}),
        (
            CallParameter,
            {"name": "value", "value": 3, "origin": EvidenceOrigin.UNKNOWN},
        ),
    ],
)
def test_unknowns_never_claim_unobserved_values(model, fields):
    with pytest.raises(ValidationError):
        model(**fields)


def test_binding_refuses_changed_capture_or_subject():
    plan, run = pair()
    changed = run.model_copy(
        update={"capture": run.capture.model_copy(update={"producer": "other"})}
    )
    with pytest.raises(ValueError, match="experiment_capture_mismatch"):
        validate_run_binding(changed, plan)
    changed = run.model_copy(update={"execution_id": "not-an-execution-id"})
    with pytest.raises(ValidationError):
        run_bytes(changed)


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), object(), {"x": object()}, "x" * 8193]
)
def test_call_parameters_use_existing_json_bounds(value):
    with pytest.raises(ValidationError):
        CallParameter(name="x", value=value, origin=EvidenceOrigin.RUNTIME)


def test_parameter_selection_is_exact_and_unique():
    plan, run = pair()
    with pytest.raises(
        ValidationError, match="experiment_call_parameter_selection_mismatch"
    ):
        run_bytes(run.model_copy(update={"call_parameters": ()}))
    with pytest.raises(ValidationError, match="experiment_duplicate_identity"):
        CaptureIdentity(
            mode=CaptureMode.SDK_SESSION,
            producer="apizr.tracking",
            producer_version="1",
            selected_parameters=("x", "x"),
        )


@pytest.mark.parametrize("reader", [read_plan, read_run])
def test_reader_refuses_unknown_version_and_oversized_artifact(reader):
    with pytest.raises(ValueError):
        reader(b'{"schema_version":"apizr.experiment-plan/v3"}')
    with pytest.raises(ValueError, match="experiment_artifact_limit"):
        reader(b" " * (4 * 1024 * 1024 + 1))


def test_published_v1_store_history_show_and_diff_preserve_every_byte():
    from hashlib import sha256

    store = ROOT / "tests/fixtures/experiments/published-0.4.5"
    manifest = json.loads((store / "sha256.json").read_bytes())
    before = {name: (store / name).read_bytes() for name in manifest["files"]}
    for name, raw in before.items():
        assert sha256(raw).hexdigest() == manifest["files"][name]
        value = read_plan(raw) if name.startswith("plans/") else read_run(raw)
        assert (
            plan_bytes(value) if name.startswith("plans/") else run_bytes(value)
        ) == raw
    history = list_runs(store)
    assert history.total == history.matched == 2
    a, b = (show_run(store, item.run_digest) for item in history.runs)
    assert run_bytes(a.run) == before[f"runs/{a.run_digest}.json"]
    assert plan_bytes(a.plan) == before[f"plans/{a.plan_digest}.json"]
    assert json.loads(history_bytes(a))["run_digest"] == a.run_digest
    difference = compare_runs(a, b)
    assert difference.source.digest.value == "same"
    assert difference.metrics[0].delta == 0.0
    assert json.loads(diff_bytes(difference))["run_a_digest"] == a.run_digest
    assert {name: (store / name).read_bytes() for name in before} == before


@pytest.mark.parametrize(
    "mode,parameters,error",
    [
        (CaptureMode.DECORATED_CALL, (), "decorated_call_function_unknown"),
        (CaptureMode.SDK_SESSION, ("x",), "call_parameters_function_unknown"),
        (CaptureMode.JUPYTER_CELL, (), "jupyter_cell_unknown"),
    ],
)
def test_required_capture_bindings_cannot_be_inferred(mode, parameters, error):
    with pytest.raises(ValueError, match="experiment_" + error):
        CaptureIdentity(
            mode=mode,
            producer="test",
            producer_version="1",
            selected_parameters=parameters,
        )


def test_intended_and_observed_v2_origins_remain_distinct():
    plan, run = pair()
    environment = EnvironmentEvidence(
        python_version=EnvironmentValue(value="3.12.13", origin=EvidenceOrigin.RUNTIME)
    )
    observed = InputArtifact(
        name="data",
        origin=EvidenceOrigin.RUNTIME,
        digest="a" * 64,
        content_origin=EvidenceOrigin.RUNTIME,
    )
    with pytest.raises(
        ValueError, match="experiment_plan_contains_runtime_observation"
    ):
        plan_bytes(plan.model_copy(update={"inputs": (observed,)}))
    with pytest.raises(
        ValueError, match="experiment_plan_contains_runtime_observation"
    ):
        plan_bytes(plan.model_copy(update={"environment": environment}))
    declared = observed.model_copy(
        update={
            "origin": EvidenceOrigin.DECLARED,
            "content_origin": EvidenceOrigin.STATIC,
        }
    )
    with pytest.raises(ValueError, match="experiment_run_contains_unobserved_evidence"):
        run_bytes(
            run.model_copy(
                update={"observed_inputs": (declared,), "environment": environment}
            )
        )
    with pytest.raises(ValueError, match="experiment_success_has_failure_diagnostics"):
        run_bytes(
            run.model_copy(
                update={
                    "diagnostics": (
                        RunDiagnostic(code="failed", origin=EvidenceOrigin.RUNTIME),
                    )
                }
            )
        )
    known_plan = plan.model_copy(
        update={
            "inputs": (declared,),
            "randomness": (
                RandomnessControl(
                    name="seed",
                    provider="numpy",
                    value=42,
                    origin=EvidenceOrigin.DECLARED,
                ),
            ),
        }
    )
    assert read_plan(plan_bytes(known_plan)).inputs[0] == declared
    known_run = run.model_copy(
        update={
            "environment": environment,
            "randomness": (
                RandomnessControl(
                    name="seed",
                    provider="numpy",
                    value=42,
                    origin=EvidenceOrigin.RUNTIME,
                ),
            ),
        }
    )
    assert read_run(run_bytes(known_run)).environment == environment


def test_v2_binding_refuses_source_substitution_and_cross_version_pair():
    plan, run = pair()
    changed = run.model_copy(
        update={
            "subject": SourceEvidence(
                identity=SourceIdentity(
                    kind="python", reference="other.py", digest="a" * 64
                ),
                origin=EvidenceOrigin.RUNTIME,
            )
        }
    )
    with pytest.raises(ValueError, match="experiment_source_mismatch"):
        validate_run_binding(changed, plan)
    v1 = read_plan((ROOT / "tests/fixtures/experiments/v1/plan.json").read_bytes())
    with pytest.raises(ValueError, match="experiment_schema_binding_mismatch"):
        validate_run_binding(
            run.model_copy(update={"plan_digest": plan_digest(v1)}), v1
        )
