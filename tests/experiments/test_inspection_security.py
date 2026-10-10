"""Source execution, framework imports, network, writes and stale output reads stay absent."""

import json
import os
import subprocess
import sys

import pytest

from apizr.experiments.inspection import inspect_experiment
from apizr.experiments.inspection_model import ExperimentInspection
from apizr.experiments.reporting import inspection_bytes

from .inspection_support import FIXTURE, project, write_source

sys.path.insert(0, str(FIXTURE.parents[3] / "scripts"))


@pytest.mark.parametrize("notebook", [False, True])
def test_guarded_installed_proof_body(notebook):
    # The same guards are run again outside checkout against each retained wheel.
    from experiment_inspection_proof import prove

    result = prove(FIXTURE, notebook=notebook)
    assert result["forbidden_calls"] == 0


def test_python_frameworks_absent_in_fresh_interpreter(tmp_path):
    path = project(tmp_path)
    script = """import sys
from apizr.experiments.inspection import inspect_experiment
names = {'pandas','numpy','sklearn','torch','tensorflow','joblib'}
assert not names.intersection(sys.modules)
result = inspect_experiment(sys.argv[1])
assert not names.intersection(sys.modules)
assert result.execution == 'not_executed'
"""
    subprocess.run(
        [sys.executable, "-I", "-B", "-c", script, str(path)], check=True, cwd=tmp_path
    )


def test_hostile_python_is_parsed_without_execution(tmp_path, monkeypatch):
    from experiment_inspection_proof import guarded_inspection

    source = """import pandas as pd
import socket
import subprocess
open('executed', 'w').write('bad')
socket.create_connection(('example.org',443))
subprocess.run(['docker', 'info'])
subprocess.run(['git', 'status'])
pd.read_csv('https://example.org/data.csv')
raise RuntimeError('private-hostile-source')
"""
    path = write_source(tmp_path, source)
    monkeypatch.chdir(tmp_path)
    result = guarded_inspection(path)
    assert not (tmp_path / "executed").exists()
    assert b"private-hostile-source" not in inspection_bytes(result)
    assert result.data.artifacts[0].digest is None


def test_parameter_literal_strings_are_explicit_source_content(tmp_path):
    result = inspect_experiment(
        write_source(tmp_path, "credential = 'explicitly-inspected-source-content'")
    )
    assert (
        result.parameters.signals[0].parameter.value
        == "explicitly-inspected-source-content"
    )
    assert b"explicitly-inspected-source-content" in inspection_bytes(result)


def test_forged_notebook_runtime_metrics_rejected(tmp_path):
    project(tmp_path)
    result = inspect_experiment(tmp_path / "fraud_detection.ipynb")
    changed = result.model_dump(mode="json")
    changed["metrics"]["signals"][0]["value"] = 0.99
    with pytest.raises(ValueError):
        ExperimentInspection.model_validate_json(json.dumps(changed))


@pytest.mark.parametrize("writer", ["path", "builtin", "descriptor"])
def test_write_guards_have_a_negative_control(tmp_path, monkeypatch, writer):
    import experiment_inspection_proof as proof

    source = write_source(tmp_path, "x = 1")
    target = tmp_path / "forbidden.txt"

    def writes(*args, **kwargs):
        if writer == "path":
            target.write_text("bad")
        elif writer == "builtin":
            with open(target, "w") as stream:
                stream.write("bad")
        else:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT, 0o600)
            os.close(descriptor)
        raise AssertionError("guard did not reject the write")

    monkeypatch.setattr(proof, "inspect_experiment", writes)
    with pytest.raises(AssertionError):
        proof.guarded_inspection(source)
    assert not target.exists()
