"""Reviewed canonical fixtures and independently versioned schema exports."""

import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from apizr.experiments import ExperimentPlan, ExperimentRun, plan_bytes, run_bytes

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/experiments/v1"


@pytest.mark.parametrize(
    "index,name,model,encode",
    [(0, "plan", ExperimentPlan, plan_bytes), (1, "run", ExperimentRun, run_bytes)],
)
def test_schema_parity_and_golden(pair, index, name, model, encode):
    schema = json.loads(
        (ROOT / f"docs/specs/apizr-experiment-{name}-v1.schema.json").read_bytes()
    )
    assert schema == model.model_json_schema()
    Draft202012Validator.check_schema(schema)
    raw = (FIXTURES / f"{name}.json").read_bytes()
    Draft202012Validator(schema).validate(json.loads(raw))
    assert encode(pair[index]) == raw
    assert encode(model.model_validate_json(raw)) == raw
    manifest = json.loads((FIXTURES / "sha256.json").read_bytes())
    assert sha256(raw).hexdigest() == manifest[name]
    assert (
        schema["properties"]["schema_version"]["const"] == f"apizr.experiment-{name}/v1"
    )
    for definition in schema["$defs"].values():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False


def test_export_is_deterministic():
    paths = [
        ROOT / f"docs/specs/apizr-experiment-{name}-v1.schema.json"
        for name in ("plan", "run")
    ]
    before = [p.read_bytes() for p in paths]
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/export_experiment_schemas.py")], check=True
    )
    assert [p.read_bytes() for p in paths] == before


def test_documented_python_pair_is_executable():
    page = (ROOT / "docs/architecture/experiment-evidence-v1.md").read_text()
    code = page.split("```python\n", 1)[1].split("```", 1)[0]
    namespace = {}
    exec(compile(code, "experiment-evidence-v1.md", "exec"), namespace)
    assert namespace["canonical_run"].endswith(b"\n")
    assert len(namespace["identity"]) == 64
