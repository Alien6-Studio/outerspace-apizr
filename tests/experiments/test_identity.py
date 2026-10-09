"""Semantic mutations, exact binding and ordering protect artifact identity."""

import json
import os
import subprocess
import sys
from hashlib import sha256

import pytest

from apizr.experiments import (
    plan_bytes,
    plan_digest,
    run_bytes,
    run_digest,
    validate_run_binding,
)


def replace_json(model, path, value):
    data = model.model_dump(mode="json")
    target = data
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    return type(model).model_validate_json(json.dumps(data))


@pytest.mark.parametrize(
    "path,value",
    [
        (("subject", "digest"), "a" * 64),
        (("subject", "executable_digest"), "b" * 64),
        (("subject", "capability_id"), "python:fraud_detection:predict"),
        (("inputs", 0, "digest"), "c" * 64),
        (("parameters", 0, "value"), 0.02),
        (("randomness", 0, "value"), 43),
        (("environment", "artifacts", 0, "digest"), "d" * 64),
        (("execution", "policy_digest"), "e" * 64),
        (("execution", "controls", 0, "value"), True),
    ],
)
def test_plan_semantic_mutations(pair, path, value):
    plan, _ = pair
    mutated = replace_json(plan, path, value)
    assert plan_digest(mutated) != plan_digest(plan)


@pytest.mark.parametrize(
    "path,value",
    [
        (("status",), "failed"),
        (("effective_parameters", 0, "value"), 0.02),
        (("environment", "python_version", "value"), "3.13.12"),
        (("metrics", 0, "value"), 0.92),
        (("outputs", 0, "digest"), "a" * 64),
        (("timing", "duration_seconds"), 2.1),
        (("randomness", 0, "value"), 43),
        (("observed_inputs", 0, "digest"), "b" * 64),
    ],
)
def test_run_mutations_preserve_bound_plan(pair, path, value):
    plan, run = pair
    before = plan_bytes(plan)
    mutated = replace_json(run, path, value)
    assert run_digest(mutated) != run_digest(run)
    assert mutated.plan_digest == plan_digest(plan) == run.plan_digest
    assert plan_bytes(plan) == before
    validate_run_binding(mutated, plan)


def test_binding_rejects_wrong_plan_digest(pair):
    plan, run = pair
    wrong = replace_json(run, ("plan_digest",), "a" * 64)
    with pytest.raises(ValueError, match="experiment_plan_digest_mismatch"):
        validate_run_binding(wrong, plan)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("digest", "a" * 64, "source"),
        ("executable_digest", "b" * 64, "source"),
        ("reference", "other/fraud_detection.ipynb", "source"),
        ("kind", "python", "source"),
        ("module", "other", "source"),
        ("capability_id", "python:fraud_detection:predict", "capability"),
    ],
)
def test_binding_rejects_source_substitution(pair, field, value, error):
    plan, run = pair
    substituted = replace_json(run, ("subject", field), value)
    with pytest.raises(ValueError, match=f"experiment_{error}_mismatch"):
        validate_run_binding(substituted, plan)


def test_selected_capability_cannot_disappear(pair):
    plan, run = pair
    plan = replace_json(
        plan, ("subject", "capability_id"), "python:fraud_detection:predict"
    )
    run = replace_json(run, ("plan_digest",), plan_digest(plan))
    with pytest.raises(ValueError, match="capability_mismatch"):
        validate_run_binding(run, plan)
    run = replace_json(run, ("subject", "capability_id"), plan.subject.capability_id)
    validate_run_binding(run, plan)


def test_canonical_roundtrip_and_hash(pair):
    for model, encode, digest in zip(
        pair, (plan_bytes, run_bytes), (plan_digest, run_digest), strict=True
    ):
        raw = encode(model)
        expected = (
            json.dumps(
                model.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode()
            + b"\n"
        )
        assert raw == expected
        assert digest(model) == sha256(raw).hexdigest()
        assert encode(type(model).model_validate_json(raw)) == raw
    validate_run_binding(pair[1], pair[0])


def test_order_independence_and_duplicates(pair):
    def reorder(value):
        if isinstance(value, dict):
            return {key: reorder(item) for key, item in reversed(value.items())}
        if isinstance(value, list):
            return [reorder(item) for item in reversed(value)]
        return value

    for model, encode in zip(pair, (plan_bytes, run_bytes), strict=True):
        data = model.model_dump(mode="json")
        assert encode(
            type(model).model_validate_json(json.dumps(reorder(data)))
        ) == encode(model)


def test_hash_seed_and_relocation(pair, tmp_path):
    results = []
    for seed in ("1", "987654"):
        root = tmp_path / seed
        root.mkdir()
        # Sources are selected relative to unrelated roots, never stored as host paths.
        source = root / "notebooks/fraud_detection.ipynb"
        source.parent.mkdir()
        source.write_bytes(b"fictional notebook source")
        assert source.relative_to(root).as_posix() == pair[0].subject.reference
        assert sha256(source.read_bytes()).hexdigest() == pair[0].subject.digest
        fixture = root / "plan.json"
        fixture.write_bytes(plan_bytes(pair[0]))
        run_fixture = root / "run.json"
        run_fixture.write_bytes(run_bytes(pair[1]))
        code = """
import json
from pathlib import Path
from apizr.experiments import ExperimentPlan, ExperimentRun, plan_bytes, run_bytes
for name, model, encode in (("plan", ExperimentPlan, plan_bytes), ("run", ExperimentRun, run_bytes)):
    data = json.loads(Path(name + ".json").read_bytes())
    reordered = {key: data[key] for key in set(data)}
    print(encode(model.model_validate_json(json.dumps(reordered))).hex())
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            env={**os.environ, "PYTHONHASHSEED": seed},
            check=True,
            capture_output=True,
        )
        assert str(root).encode() not in plan_bytes(pair[0])
        results.append(result.stdout)
    assert results[0] == results[1]


@pytest.mark.parametrize(
    "which,path",
    [
        (0, "inputs"),
        (0, "parameters"),
        (0, "randomness"),
        (0, "environment.packages"),
        (0, "environment.artifacts"),
        (0, "execution.controls"),
        (1, "observed_inputs"),
        (1, "effective_parameters"),
        (1, "randomness"),
        (1, "environment.packages"),
        (1, "environment.artifacts"),
        (1, "metrics"),
        (1, "outputs"),
        (1, "diagnostics"),
    ],
)
def test_each_named_collection_orders_distinct_records(pair, which, path):
    data = pair[which].model_dump(mode="json")
    target = data
    for part in path.split(".")[:-1]:
        target = target[part]
    field = path.split(".")[-1]
    if field == "diagnostics":
        data["status"] = "failed"
        first = {"code": "z_failure", "origin": "runtime"}
        key = "code"
    else:
        first = {**target[field][0], "name": "z_record"}
        key = "name"
    second = {**first, key: "a_record"}
    target[field] = [first, second]
    model = type(pair[which])
    encode = (plan_bytes, run_bytes)[which]
    unordered = encode(model.model_validate_json(json.dumps(data)))
    target[field].reverse()
    assert encode(model.model_validate_json(json.dumps(data))) == unordered
    target[field].append(first)
    with pytest.raises(ValueError, match="duplicate_identity"):
        model.model_validate_json(json.dumps(data))


def test_parameter_object_order_is_irrelevant_but_array_order_matters(pair):
    plan = replace_json(pair[0], ("parameters", 0, "value"), {"b": [1, 2], "a": "café"})
    reordered = replace_json(
        plan, ("parameters", 0, "value"), {"a": "café", "b": [1, 2]}
    )
    changed = replace_json(plan, ("parameters", 0, "value"), {"a": "café", "b": [2, 1]})
    assert plan_bytes(plan) == plan_bytes(reordered)
    assert plan_digest(plan) != plan_digest(changed)
    assert "café".encode() in plan_bytes(plan)
