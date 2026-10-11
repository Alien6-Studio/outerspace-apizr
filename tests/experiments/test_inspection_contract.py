"""Reject invented states, runtime claims, loose nested objects and forged identities."""

import json

import pytest

from apizr.experiments import (
    EnvironmentEvidence,
    EnvironmentValue,
    EvidenceOrigin,
)
from apizr.experiments.inspection import inspect_experiment
from apizr.experiments.inspection_model import ExperimentInspection, ServingEvidence
from apizr.experiments.reporting import inspection_bytes
from apizr.readiness import State

from .inspection_support import project, write_source


def replace_json(result, pointer, value):
    data = result.model_dump(mode="json")
    target = data
    parts = pointer.split("/")
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    target[int(parts[-1]) if isinstance(target, list) else parts[-1]] = value
    return json.dumps(data)


@pytest.mark.parametrize(
    "pointer,value",
    [
        ("extra", True),
        ("execution", "executed"),
        ("schema_version", "v2"),
        ("fingerprint_policy/max_file_bytes", "10"),
        ("code/reference", "/tmp/train.py"),
        ("code/source/module", "other"),
        ("code/signal_digest/value", "0" * 64),
        ("code/readiness_digest/value", "0" * 64),
        ("code/ir_digest/value", "0" * 64),
        ("serving/capabilities", []),
        ("serving/capabilities/0/id", "experiment:train:predict"),
        ("serving/capabilities/0/module", "other"),
        ("serving/capabilities/0/source_path", "other.py"),
        ("serving/capabilities/0/source_digest/value", "0" * 64),
        ("serving/capabilities/0/ir_digest/value", "0" * 64),
        ("serving/capabilities/0/readiness_digest/value", "0" * 64),
        ("serving/capabilities/0/span/line", 1),
        ("serving/capabilities/0/readiness", "ready"),
        ("serving/capabilities/0/can_generate_interface", True),
        ("metrics/signals/0/value", 0.99),
        ("outputs/signals/0/digest", "0" * 64),
        ("parameters/signals/0/parameter/origin", "runtime"),
        ("data/artifacts/0/origin", "runtime"),
        ("data/artifacts/0/content_origin", "runtime"),
        ("randomness/controls/1/origin", "runtime"),
        ("environment/evidence/python_version", {"origin": "runtime", "value": "3.12"}),
        ("environment/evidence/artifacts/0/origin", "declared"),
        ("environment/evidence/artifacts/0/content_origin", "runtime"),
        ("locations/0/evidence", "/data/artifacts/999"),
        ("locations/0/location/source", "other.py"),
        ("metrics/signals/0/source", "other.py"),
    ],
)
def test_reject_forged_machine_evidence(tmp_path, pointer, value):
    result = inspect_experiment(project(tmp_path))
    with pytest.raises(ValueError):
        ExperimentInspection.model_validate_json(
            replace_json(result, pointer, value), strict=True
        )


def test_revalidate_unchecked_nested_contract_instances(tmp_path):
    result = inspect_experiment(project(tmp_path))
    assessment = result.serving.readiness.assessments[0].model_copy(
        update={"state": State.READY}
    )
    forged = result.serving.readiness.model_copy(update={"assessments": (assessment,)})
    with pytest.raises(ValueError):
        ServingEvidence(readiness=forged, capabilities=result.serving.capabilities)
    with pytest.raises(ValueError, match="duplicate"):
        ServingEvidence(
            readiness=result.serving.readiness,
            capabilities=result.serving.capabilities * 2,
        )
    bad = result.model_copy(
        update={"states": result.states.model_copy(update={"metrics": "captured"})}
    )
    with pytest.raises(ValueError):
        inspection_bytes(bad)


def test_unknown_environment_facts_are_not_runtime_claims(tmp_path):
    result = inspect_experiment(write_source(tmp_path, ""))
    evidence = EnvironmentEvidence(
        python_version=EnvironmentValue(value=None, origin=EvidenceOrigin.UNKNOWN)
    )
    changed = result.model_copy(
        update={
            "environment": result.environment.model_copy(update={"evidence": evidence})
        }
    )
    assert (
        ExperimentInspection.model_validate(changed).states.environment.value
        == "unknown"
    )


def test_location_position_and_notebook_consistency(tmp_path):
    result = inspect_experiment(project(tmp_path))
    index = next(
        i
        for i, loc in enumerate(result.locations)
        if loc.evidence == "/parameters/signals/0"
    )
    with pytest.raises(ValueError, match="position_mismatch"):
        ExperimentInspection.model_validate_json(
            replace_json(result, f"locations/{index}/location/line", 999)
        )
    data = result.model_dump(mode="json")
    data["locations"][0]["location"].update(
        cell_index=0, code_cell_index=0, cell_line=1
    )
    with pytest.raises(ValueError, match="source_mismatch"):
        ExperimentInspection.model_validate_json(json.dumps(data))


def test_code_diagnostic_cannot_refer_to_another_module(tmp_path):
    result = inspect_experiment(write_source(tmp_path, "def f(): pass\ndef f(): pass"))
    with pytest.raises(ValueError, match="diagnostic_source_mismatch"):
        ExperimentInspection.model_validate_json(
            replace_json(result, "code/diagnostics/0/source/module", "other")
        )


@pytest.mark.parametrize("value", [1, "true", "1"])
def test_nested_canonical_values_do_not_coerce_by_default(tmp_path, value):
    result = inspect_experiment(
        write_source(tmp_path, "def predict(x: float): return x")
    )
    with pytest.raises(ValueError):
        ExperimentInspection.model_validate_json(
            replace_json(result, "serving/readiness/assessments/0/in_ir", value)
        )


def test_unserializable_canonical_value_is_validation_error(tmp_path):
    result = inspect_experiment(write_source(tmp_path, ""))
    data = result.code.model_dump()
    data["source"] = object()
    with pytest.raises(ValueError, match="canonical_value_invalid"):
        type(result.code).model_validate(data)
