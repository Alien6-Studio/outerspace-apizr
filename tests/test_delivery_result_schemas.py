"""Portable structural schemas remain derived from current v1 models."""

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from apizr.delivery_results import (
    AdmissionResult,
    BuildResult,
    DeliveryResult,
    ObservationResult,
    PublishResult,
    PushResult,
)


@pytest.mark.parametrize(
    "model",
    [
        BuildResult,
        PushResult,
        DeliveryResult,
        PublishResult,
        AdmissionResult,
        ObservationResult,
    ],
)
def test_published_result_schema_matches_v1_contract(model):
    schema = model.model_json_schema()
    name = (
        schema["properties"]["schema"]["default"].replace(".", "-", 1).replace("/", "-")
    )
    path = Path(__file__).parents[1] / "docs/specs" / (name + ".schema.json")
    assert json.loads(path.read_text()) == schema
    Draft202012Validator.check_schema(schema)


def test_ab_example_changes_content_identity_not_logical_identity(tmp_path):
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(
        "governance_proof", root / "scripts/governance_evidence_proof.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    record = module.exercise(root / "examples/governance", tmp_path / "proof")
    assert record["registry_executed"] is False and record["trunx_executed"] is False
    assert record["variants"]["a"]["observed_total_cents"] == 300
    assert record["variants"]["b"]["observed_total_cents"] == 350
