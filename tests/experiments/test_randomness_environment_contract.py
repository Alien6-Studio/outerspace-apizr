"""Evidence changes identities without changing source/data or proving causality."""

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from apizr.experiments import (
    EnvironmentEvidence,
    EnvironmentValue,
    ExperimentPlan,
    ExperimentRun,
    PackageEvidence,
    RandomnessControl,
    capture_runtime_environment,
    discover_environment_specs,
    discover_randomness,
    plan_bytes,
    plan_digest,
    run_bytes,
    run_digest,
    validate_run_binding,
)
from apizr.experiments import EvidenceOrigin as O
from tests.experiments.conftest import example_pair


def test_seed_ab_keeps_source_data_capability_and_parameters(pair):
    plan, _ = pair
    a = plan.model_copy(
        update={
            "randomness": discover_randomness(
                "import numpy as np\nnp.random.seed(42)", source_reference="train.py"
            ).controls
        }
    )
    b = plan.model_copy(
        update={
            "randomness": discover_randomness(
                "import numpy as np\nnp.random.seed(43)", source_reference="train.py"
            ).controls
        }
    )
    assert a.subject == b.subject == plan.subject
    assert a.subject.capability_id == b.subject.capability_id
    assert a.inputs == b.inputs and a.parameters == b.parameters
    assert a.environment == b.environment and a.execution == b.execution
    assert a.randomness != b.randomness and plan_digest(a) != plan_digest(b)


def test_lock_ab_static_plan_and_runtime_run(tmp_path, pair):
    plan, run = pair
    (tmp_path / "uv.lock").write_bytes(b"package A\n")
    static_a = discover_environment_specs(tmp_path).evidence
    runtime_a = capture_runtime_environment(root=tmp_path).evidence
    (tmp_path / "uv.lock").write_bytes(b"package B\n")
    static_b = discover_environment_specs(tmp_path).evidence
    runtime_b = capture_runtime_environment(root=tmp_path).evidence
    assert static_a.artifacts[0].digest != static_b.artifacts[0].digest
    assert plan_digest(
        plan.model_copy(update={"environment": static_a})
    ) != plan_digest(plan.model_copy(update={"environment": static_b}))
    assert run_digest(run.model_copy(update={"environment": runtime_a})) != run_digest(
        run.model_copy(update={"environment": runtime_b})
    )
    assert static_a.artifacts[0].origin is O.STATIC
    assert runtime_a.artifacts[0].origin is O.RUNTIME


def test_architecture_provenance_not_bypassed(pair):
    plan, run = pair
    static = EnvironmentEvidence(
        architecture=EnvironmentValue(value="arm64", origin=O.STATIC)
    )
    runtime = EnvironmentEvidence(
        architecture=EnvironmentValue(value="arm64", origin=O.RUNTIME)
    )
    plan_bytes(plan.model_copy(update={"environment": static}))
    run_bytes(run.model_copy(update={"environment": runtime}))
    with pytest.raises(ValidationError, match="runtime_observation"):
        plan_bytes(plan.model_copy(update={"environment": runtime}))
    with pytest.raises(ValidationError, match="unobserved_evidence"):
        run_bytes(run.model_copy(update={"environment": static}))
    assert "architecture" not in EnvironmentEvidence().model_dump()


@given(st.integers(min_value=0, max_value=2**32 - 2))
@settings(max_examples=30, deadline=None)
def test_seed_identity_and_control_order(seed):
    plan, _ = example_pair()
    controls = tuple(
        RandomnessControl(provider=provider, name="seed", value=seed, origin=O.STATIC)
        for provider in ("numpy", "python.random")
    )
    a = plan.model_copy(update={"randomness": controls})
    reordered = plan.model_copy(update={"randomness": controls[::-1]})
    changed = plan.model_copy(
        update={
            "randomness": (
                controls[0].model_copy(update={"value": seed + 1}),
                controls[1],
            )
        }
    )
    assert plan_bytes(a) == plan_bytes(reordered)
    assert plan_digest(a) != plan_digest(changed)


@given(st.integers(min_value=0, max_value=10000))
@settings(max_examples=30, deadline=None)
def test_package_ab_run_identity_and_package_order(version):
    plan, run = example_pair()
    identity = plan_digest(plan)
    packages = (
        PackageEvidence(name="numpy", version=f"2.4.{version}", origin=O.RUNTIME),
        PackageEvidence(name="outerspace-apizr", version="0.4.4", origin=O.RUNTIME),
    )
    a = run.model_copy(update={"environment": EnvironmentEvidence(packages=packages)})
    b = run.model_copy(
        update={
            "environment": EnvironmentEvidence(
                packages=(
                    packages[0].model_copy(update={"version": f"2.4.{version + 1}"}),
                    packages[1],
                )
            )
        }
    )
    assert a.environment == EnvironmentEvidence(packages=packages[::-1])
    assert a.environment != b.environment and run_digest(a) != run_digest(b)
    assert plan_digest(plan) == identity == a.plan_digest == b.plan_digest
    validate_run_binding(a, plan)
    validate_run_binding(b, plan)


def test_no_deterministic_flags_in_canonical_schema():
    for model in (ExperimentPlan, ExperimentRun):
        schema = json.dumps(model.model_json_schema())
        for name in (
            "reproducible",
            "deterministic",
            "confidence",
            "reproducibility_score",
        ):
            assert f'"{name}"' not in schema


def test_environment_variable_changes_not_evidence(monkeypatch, pair, capsys):
    sentinel = "SUPER_SECRET_TEST_VALUE"
    monkeypatch.setenv(sentinel, "private-value-first")
    a = capture_runtime_environment()
    monkeypatch.setenv(sentinel, "private-value-second")
    b = capture_runtime_environment()
    assert a == b
    raw = run_bytes(pair[1].model_copy(update={"environment": a.evidence}))
    assert sentinel.encode() not in raw and b"private-value" not in raw
    assert (
        sentinel not in a.model_dump_json()
        and "private-value" not in a.model_dump_json()
    )
    assert capsys.readouterr() == ("", "")


def test_documented_randomness_example():
    page = (
        Path(__file__).parents[2] / "docs/guides/experiment-randomness-environment.md"
    ).read_text()
    code = (
        page.split("<!-- executable-randomness-example -->", 1)[1]
        .split("```python\n", 1)[1]
        .split("```", 1)[0]
    )
    namespace = {}
    exec(compile(code, "experiment-randomness-environment.md", "exec"), namespace)
    assert namespace["controls"][0].value == 42
