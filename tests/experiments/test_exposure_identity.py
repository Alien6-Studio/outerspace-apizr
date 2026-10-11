"""Frozen fictional bridge evidence, schema and cross-process bundle parity."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from apizr.experiments.exposure_model import ExperimentExposureBinding, exposure_bytes
from apizr.experiments.store import RunRecord

from .test_exposure import compile_case

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/experiments/exposure"


def test_bridge_schema_and_new_canonical_goldens(tmp_path):
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "docs/specs/apizr-experiment-exposure-v1.schema.json"
    )
    schema = json.loads(schema_path.read_bytes())
    assert schema == ExperimentExposureBinding.model_json_schema()
    Draft202012Validator.check_schema(schema)
    record = RunRecord.model_validate_json((FIXTURES / "record.json").read_bytes())
    shutil.copytree(FIXTURES / "project", tmp_path / "project")
    for interface in ("rest", "mcp"):
        result = compile_case(
            (tmp_path / "project/serving.py", record),
            interface=interface,
            dependencies=("example-package",),
        )
        raw = exposure_bytes(result.result.binding)
        assert raw == (FIXTURES / f"{interface}-binding.json").read_bytes()
        Draft202012Validator(schema).validate(json.loads(raw))


def test_hashseed_and_relocation_determinism(tmp_path):
    script = """import sys
from pathlib import Path
from hashlib import sha256
from apizr.experiments.store import RunRecord
from apizr.experiments.exposure import expose_run
from apizr.workspace.operator_policy import OperatorPolicy
root=Path(sys.argv[1])
record=RunRecord.model_validate_json(Path(sys.argv[2]).read_bytes())
authority=OperatorPolicy.model_validate({'schema':'apizr.operator-policy/v1','grants':({'adapter':'repository','operation':'analyze','target':{'kind':'local','root':str(root)},'permissions':('source.analyze',)},)})
for interface in ('rest','mcp'):
    result=expose_run(record,root,capability='python:serving:predict',interface=interface,artifacts=('model',),operator_policy=authority)
    print([(name,sha256(data).hexdigest()) for name,data in sorted(result.bundle.items())])
"""
    values = []
    for seed in ("0", "127"):
        root = tmp_path / seed
        shutil.copytree(FIXTURES / "project", root)
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                script,
                str(root),
                str(FIXTURES / "record.json"),
            ],
            cwd=tmp_path,
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        values.append(completed.stdout)
    assert values[0] == values[1]
