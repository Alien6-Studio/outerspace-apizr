"""Composition, deterministic identities, evidence states and source-local serving."""

import json
from hashlib import sha256

import pytest
from jsonschema import Draft202012Validator

from apizr.capabilities.inspection import inspect_source
from apizr.experiments import EvidenceOrigin, FingerprintPolicy, parse_input_declaration
from apizr.experiments.inspection import inspect_experiment
from apizr.experiments.inspection_model import ExperimentInspection
from apizr.experiments.reporting import inspection_bytes, text_report

from .inspection_support import FIXTURE, project, write_source


def test_realistic_python_composes_existing_evidence(tmp_path):
    path = project(tmp_path)
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts/fraud.joblib").write_bytes(b"stale output MUST NOT be read")
    result = inspect_experiment(path)
    assert result.execution == "not_executed"
    assert result.states.model_dump(mode="json") == {
        "code": "captured",
        "data": "partial",
        "parameters": "partial",
        "randomness": "uncontrolled",
        "environment": "partial",
        "metrics": "partial",
        "outputs": "partial",
        "serving": "partial",
    }
    data, remote = result.data.artifacts
    assert (data.reference, data.digest, data.size) == (
        "data/train.csv",
        sha256((tmp_path / "data/train.csv").read_bytes()).hexdigest(),
        24,
    )
    assert data.content_origin == EvidenceOrigin.STATIC
    assert remote.uri == "s3://examples/validation.parquet" and remote.digest is None
    assert "dynamic_input_reference" in {d.code for d in result.data.diagnostics}
    assert [s.parameter.name for s in result.parameters.signals] == [
        "learning_rate",
        "max_depth",
        "n_estimators",
        "model_name",
    ]
    assert [s.name for s in result.metrics.signals] == ["roc_auc", "precision"]
    assert result.outputs.signals[0].declaration.reference == "artifacts/fraud.joblib"
    assert result.environment.evidence.python_version is None
    existing = inspect_source(path.read_bytes(), module_name="train")
    assert result.code.source == existing.capability_ir.source
    assert result.code.ir_digest == existing.ir_digest
    assert result.code.readiness_digest == existing.readiness_digest
    assert result.serving.readiness == existing.readiness
    assert result.serving.capabilities[0].id == "python:train:predict"
    assert (
        result.serving.capabilities[0].span
        == existing.capability_ir.capabilities[0].source
    )
    assert result.serving.readiness.structured_types[0].name == "PredictionInput"
    assert result.serving.readiness.structured_types[0].type.kind == "object"
    payload = inspection_bytes(result)
    assert str(tmp_path).encode() not in payload
    assert b"stale output MUST NOT" not in payload
    assert b"return float(model" not in payload
    assert b"accuracy: 0.999" not in payload
    assert ExperimentInspection.model_validate_json(payload, strict=True) == result
    Draft202012Validator(ExperimentInspection.model_json_schema()).validate(
        json.loads(payload)
    )


def test_relocation_and_repeat_are_byte_identical(tmp_path):
    a, b = project(tmp_path / "one"), project(tmp_path / "two")
    assert (
        inspection_bytes(inspect_experiment(a))
        == inspection_bytes(inspect_experiment(a))
        == inspection_bytes(inspect_experiment(b))
    )


@pytest.mark.parametrize(
    "source, section, state",
    [
        ("", "data", "unknown"),
        ("", "parameters", "unknown"),
        ("", "randomness", "unknown"),
        ("", "environment", "unknown"),
        ("", "metrics", "unknown"),
        ("", "outputs", "unknown"),
        ("", "serving", "unknown"),
        ("learning_rate=0.05", "parameters", "captured"),
        ("learning_rate=choose()", "parameters", "partial"),
        ("import random\nrandom.seed(42)", "randomness", "captured"),
        ("import random\nrandom.seed(config.seed)", "randomness", "partial"),
        ("import random\nrandom.seed(1)\nrandom.seed(2)", "randomness", "partial"),
        ("import numpy as np\nnp.random.default_rng()", "randomness", "uncontrolled"),
        ("import torch\ntorch.manual_seed(42)", "randomness", "partial"),
        ("import tensorflow as tf\ntf.random.set_seed(42)", "randomness", "partial"),
        ("import pandas as pd\npd.read_csv('data.csv')", "data", "captured"),
        ("import pandas as pd\npd.read_csv(PATH)", "data", "partial"),
        ("import pandas as pd\npd.read_csv('missing.csv')", "data", "partial"),
        (
            "import pandas as pd\npd.read_csv('s3://bucket/train.csv')",
            "data",
            "partial",
        ),
        (
            "from sklearn.metrics import roc_auc_score\nroc_auc_score(x,y)",
            "metrics",
            "partial",
        ),
        ("import joblib\njoblib.dump(model, 'out.joblib')", "outputs", "partial"),
        ("import joblib\njoblib.dump(model, PATH)", "outputs", "partial"),
        ("def predict(x: float) -> float:\n return x", "serving", "partial"),
    ],
)
def test_derived_states(tmp_path, source, section, state):
    (tmp_path / "data.csv").write_bytes(b"a\n1\n")
    result = inspect_experiment(write_source(tmp_path, source))
    assert getattr(result.states, section).value == state
    changed = result.model_dump(mode="json")
    changed["states"][section] = "captured" if state != "captured" else "unknown"
    with pytest.raises(ValueError, match="states_disagree"):
        ExperimentInspection.model_validate_json(json.dumps(changed))
    changed["states"][section] = "not_applicable"
    with pytest.raises(ValueError, match="states_disagree"):
        ExperimentInspection.model_validate_json(json.dumps(changed))


def test_explicit_inputs_and_bounded_reads(tmp_path):
    path = write_source(tmp_path, "import pandas as pd\npd.read_csv(PATH)")
    (tmp_path / "data.csv").write_bytes(b"a\n1\n")
    declaration = parse_input_declaration("training=data.csv")
    result = inspect_experiment(path, declarations=(declaration,))
    assert result.data.artifacts[0].origin == EvidenceOrigin.DECLARED
    assert result.data.artifacts[0].content_origin == EvidenceOrigin.STATIC
    assert any(d.code == "dynamic_input_reference" for d in result.data.diagnostics)
    assert result.states.data.value == "partial"
    limited = inspect_experiment(
        path,
        declarations=(declaration,),
        fingerprint_policy=FingerprintPolicy(max_file_bytes=1),
    )
    assert limited.data.artifacts[0].digest is None
    assert "input_too_large" in {d.code for d in limited.data.diagnostics}


def test_custom_root_and_module(tmp_path):
    (tmp_path / "src").mkdir()
    path = write_source(
        tmp_path / "src", "def predict(x: float): return x", name="not-a-module.py"
    )
    result = inspect_experiment(path, root=tmp_path, module_name="fraud.model")
    assert result.code.reference == "src/not-a-module.py"
    assert result.serving.capabilities[0].id == "python:fraud.model:predict"


def test_canonical_identity_is_preserved_for_valid_source(tmp_path):
    source = write_source(tmp_path, "def predict(x: float): return x")
    try:
        result = inspect_experiment(source)
    except ValueError as error:
        raise AssertionError(
            "Valid source must yield existing capability identities"
        ) from error
    assert result.serving.capabilities[0].id == "python:train:predict"


@pytest.mark.parametrize(
    "failure",
    [
        "kind",
        "outside",
        "module",
        "missing",
        "invalid",
        "large",
        "symlink",
        "directory",
    ],
)
def test_source_refusals(tmp_path, failure):
    path = write_source(tmp_path, "x = 1")
    options = {}
    if failure == "kind":
        path = write_source(tmp_path, "x = 1", "train.txt")
    elif failure == "outside":
        options["root"] = tmp_path / "subdir"
    elif failure == "module":
        options["module_name"] = "../bad"
    elif failure == "missing":
        path.unlink()
    elif failure == "invalid":
        path.write_text("x =")
    elif failure == "large":
        path.write_bytes(b"#" * (1024**2 + 1))
    elif failure == "symlink":
        target = tmp_path / "alias.py"
        target.symlink_to(path)
        path = target
    else:
        path.unlink()
        path.mkdir()
    with pytest.raises((ValueError, OSError, SyntaxError)):
        inspect_experiment(path, **options)


def test_text_order_specifics_and_concise_sample(tmp_path):
    result = inspect_experiment(project(tmp_path))
    text = text_report(result)
    headings = [line.split(" — ")[0] for line in text.splitlines() if " — " in line]
    assert headings == [
        "Code",
        "Data",
        "Parameters",
        "Randomness",
        "Environment",
        "Metrics",
        "Outputs",
        "Serving",
    ]
    for fact in (
        "data/train.csv",
        "sha256:",
        "24 bytes",
        "learning_rate = 0.05",
        "uncontrolled randomness",
        "value not observed",
        "output not observed",
        "python:train:predict",
        "repository context not assessed",
    ):
        assert fact in text
    assert len(text.splitlines()) <= 40
    assert "return float" not in text


def test_committed_schema_parity():
    root = FIXTURE.parents[3]
    committed = json.loads(
        (root / "docs/specs/apizr-experiment-inspection-v1.schema.json").read_text()
    )
    assert committed == ExperimentInspection.model_json_schema()


def test_bounded_randomness_trace_and_invalid_input_location(tmp_path):
    path = write_source(tmp_path, "import random\n" + "random.seed(None)\n" * 513)
    result = inspect_experiment(path)
    assert not result.randomness.controls
    assert result.randomness.diagnostics[0].code == "randomness_discovery_limit"
    assert result.states.randomness.value == "partial"
    path.write_text("import pandas as pd\npd.read_csv('/private/invalid.csv')")
    result = inspect_experiment(path)
    assert not result.data.artifacts
    assert result.data.diagnostics[0].code == "nonportable_input_reference"


def test_human_locationless_declared_missing_input(tmp_path):
    result = inspect_experiment(
        write_source(tmp_path, ""),
        declarations=(parse_input_declaration("explicit=missing.csv"),),
    )
    assert "missing.csv: content unverified" in text_report(result)
    assert "input missing" in text_report(result)


def test_human_bounded_literal_and_source_diagnostics(tmp_path):
    source = "model_name = " + repr("x" * 120) + "\ndef f(): pass\ndef f(): pass\n"
    result = inspect_experiment(write_source(tmp_path, source))
    report = text_report(result)
    assert "…" in report and "source diagnostics" in report
