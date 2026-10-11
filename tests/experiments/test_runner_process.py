"""Real fresh-process workloads, evidence semantics and sanitized failures."""

import json
import os
import sys
from hashlib import sha256

import pytest

from apizr.experiments.history import list_runs, show_run
from apizr.experiments.inputs import parse_input_declaration
from apizr.experiments.inspection import inspect_experiment
from apizr.experiments.outputs import parse_output_declaration
from apizr.experiments.planning import RunOptions, derive_plan, parse_metric_binding
from apizr.experiments.runner import execute_plan, run_experiment
from apizr.experiments.serialization import validate_run_binding
from apizr.experiments.store import DEFAULT_STORE


def script(root, text):
    path = root / "train.py"
    path.write_text(text)
    return path


def test_real_process_bindings_environment_data_outputs_and_history(tmp_path):
    (tmp_path / "helper.py").write_text("VALUE = 7")
    (tmp_path / "input.csv").write_bytes(b"x\n3\n")
    source = script(
        tmp_path,
        """import os, sys, random
from pathlib import Path
from helper import VALUE
random.seed(42)
rate = 0.1
rate *= 2
score = {"value": [VALUE, None, True]}
assert __name__ == "__main__" and __file__ == "train.py"
assert Path.cwd().joinpath("input.csv").read_bytes() == b"x\\n3\\n"
worker = {"pid": os.getpid(), "executable": sys.executable, "root": str(Path.cwd())}
print("stdout_secret_sentinel")
os.write(1, b"raw_stdout_secret_sentinel")
os.write(2, b"stderr_secret_sentinel")
Path("model.bin").write_bytes(b"MODEL")
""",
    )
    record = run_experiment(
        source,
        declarations=(parse_input_declaration("train=input.csv"),),
        options=RunOptions(
            metrics=(
                parse_metric_binding("score=score"),
                parse_metric_binding("worker=worker"),
            ),
            outputs=(parse_output_declaration("model=model.bin"),),
        ),
    )
    plan, run = record.plan, record.run
    validate_run_binding(run, plan)
    assert run.status == "success"
    assert run.environment.python_version.value == ".".join(
        map(str, sys.version_info[:3])
    )
    assert [p.name for p in run.environment.packages] == ["outerspace-apizr"]
    assert all(o.value in ("runtime", "unknown") for o in run.environment.origins())
    assert plan.randomness and not run.randomness
    assert {p.name: p.value for p in run.effective_parameters}["rate"] == 0.2
    assert {p.name: p.value for p in plan.parameters}["rate"] == 0.1
    metrics = {m.name: m.value for m in run.metrics}
    assert metrics["score"] == {"value": (7, None, True)}
    assert metrics["worker"]["pid"] != os.getpid()
    assert metrics["worker"]["executable"] == sys.executable
    assert metrics["worker"]["root"] == str(tmp_path)
    assert run.observed_inputs[0].digest == sha256(b"x\n3\n").hexdigest()
    assert run.observed_inputs[0].content_origin.value == "runtime"
    assert run.outputs[0].digest == sha256(b"MODEL").hexdigest()
    assert run.outputs[0].size == 5
    assert run.timing.ended_at >= run.timing.started_at
    assert run.timing.duration_seconds > 0
    history = tmp_path / DEFAULT_STORE
    assert list_runs(history).runs[0].run_digest == record.run_digest
    assert show_run(history, record.run_digest[:12]) == record
    assert all(
        b"secret_sentinel" not in p.read_bytes() for p in history.rglob("*.json")
    )
    repeated = run_experiment(source, options=RunOptions())
    assert repeated.run_digest != record.run_digest


@pytest.mark.parametrize(
    "body,status,code",
    [
        ("pass", "success", None),
        ("raise SystemExit", "success", None),
        ("raise SystemExit(0)", "success", None),
        ("raise SystemExit(2)", "failed", "execution_exit"),
        ('raise SystemExit("exception_secret")', "failed", "execution_exit"),
        ('raise RuntimeError("exception_secret")', "failed", "execution_exception"),
        ("raise KeyboardInterrupt", "cancelled", "execution_cancelled"),
        ("import os; os._exit(7)", "failed", "worker_failed"),
    ],
)
def test_status_sanitized_and_failed_outputs_never_captured(
    tmp_path, body, status, code
):
    (tmp_path / "model.bin").write_bytes(b"STALE")
    source = script(
        tmp_path, 'from pathlib import Path\nPath("once").open("a").write("x")\n' + body
    )
    record = run_experiment(
        source,
        options=RunOptions(outputs=(parse_output_declaration("model=model.bin"),)),
    )
    assert record.run.status == status
    assert [d.code for d in record.run.diagnostics] == ([code] if code else [])
    assert (tmp_path / "once").read_text() == "x"
    assert "exception_secret" not in record.model_dump_json()
    if status != "success":
        assert record.run.outputs == ()
    assert show_run(tmp_path / DEFAULT_STORE, record.run_digest) == record


@pytest.mark.parametrize("mode", ["clean", "selected", "inherit"])
def test_environment_modes_do_not_serialize_secrets(tmp_path, monkeypatch, mode):
    monkeypatch.setenv("APIZR_PRIVATE_TEST", "environment_secret_sentinel")
    monkeypatch.setenv("APIZR_OMITTED_TEST", "other_secret_sentinel")
    monkeypatch.setenv("PYTHONPATH", "/unusable/ambient/project")
    options = RunOptions(
        environment_names=("APIZR_PRIVATE_TEST", "ABSENT_NAME")
        if mode == "selected"
        else (),
        inherit_environment=mode == "inherit",
        metrics=(parse_metric_binding("visible=visible"),),
    )
    source = script(
        tmp_path,
        'import os\nvisible = ["APIZR_PRIVATE_TEST" in os.environ, "APIZR_OMITTED_TEST" in os.environ]\n',
    )
    record = run_experiment(source, options=options)
    assert record.run.status == "success"
    assert (
        record.run.metrics[0].value
        == {
            "clean": (False, False),
            "selected": (True, False),
            "inherit": (True, True),
        }[mode]
    )
    assert "secret_sentinel" not in record.model_dump_json()


@pytest.mark.parametrize("mutation", ["source", "input"])
def test_preflight_mutation_refuses_before_effects(tmp_path, mutation):
    (tmp_path / "data.csv").write_text("before")
    source = script(tmp_path, 'from pathlib import Path\nPath("EXECUTED").touch()')
    inspection = inspect_experiment(
        source, declarations=(parse_input_declaration("data=data.csv"),)
    )
    plan = derive_plan(inspection)
    (source if mutation == "source" else tmp_path / "data.csv").write_text("after")
    with pytest.raises(ValueError, match=f"{mutation}_changed"):
        execute_plan(inspection, plan, root=tmp_path)
    assert not (tmp_path / "EXECUTED").exists()


def test_input_mutation_during_workload_fails_without_choosing_a_digest(tmp_path):
    (tmp_path / "data.csv").write_text("before")
    source = script(
        tmp_path,
        'from pathlib import Path\nPath("data.csv").write_text("after")\nPath("model").write_text("new")',
    )
    record = run_experiment(
        source,
        declarations=(parse_input_declaration("data=data.csv"),),
        options=RunOptions(outputs=(parse_output_declaration("model=model"),)),
    )
    assert record.run.status == "failed"
    assert [d.code for d in record.run.diagnostics] == [
        "input_changed_during_execution"
    ]
    assert not record.run.observed_inputs and not record.run.outputs


@pytest.mark.parametrize("value", ["missing", "object()", 'float("nan")', "[1] * 1025"])
def test_required_metric_invalid_is_persisted_failure(tmp_path, value):
    source = script(tmp_path, "pass" if value == "missing" else f"result = {value}")
    record = run_experiment(
        source, options=RunOptions(metrics=(parse_metric_binding("metric=result"),))
    )
    assert record.run.status == "failed"
    assert record.run.diagnostics[0].code == "metric_capture_failed"
    assert not record.run.metrics


def test_required_missing_output_is_persisted_failure(tmp_path):
    record = run_experiment(
        script(tmp_path, "pass"),
        options=RunOptions(outputs=(parse_output_declaration("model=missing"),)),
    )
    assert record.run.status == "failed"
    assert record.run.diagnostics[0].code == "output_capture_failed"


def test_unverified_remote_input_is_never_fetched(tmp_path):
    record = run_experiment(
        script(tmp_path, "pass"),
        declarations=(
            parse_input_declaration("data=https://example.invalid/data.csv"),
        ),
    )
    assert record.run.status == "success"
    assert record.run.observed_inputs[0].digest is None
    assert record.run.observed_inputs[0].content_origin.value == "unknown"


def test_zero_mod_metric_and_output_use_controlled_fake_packages(tmp_path):
    package = tmp_path / "sklearn"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "metrics.py").write_text("def roc_auc_score(y, p):\n    return 0.75\n")
    (tmp_path / "joblib.py").write_text(
        'from pathlib import Path\ndef dump(value, path):\n    Path(path).write_bytes(b"output")\n'
    )
    source = script(
        tmp_path,
        'from sklearn.metrics import roc_auc_score\nimport joblib\nauc = roc_auc_score([1], [1])\njoblib.dump(None, "model.bin")\nif False:\n    joblib.dump(None, "missing.bin")\n',
    )
    record = run_experiment(source)
    assert record.run.status == "success"
    assert [(m.name, m.value) for m in record.run.metrics] == [("roc_auc", 0.75)]
    assert len(record.run.outputs) == 1
    assert record.run.outputs[0].digest == sha256(b"output").hexdigest()
    assert {p.name for p in record.run.environment.packages} == {
        "outerspace-apizr",
        "scikit-learn",
        "joblib",
    }


def test_notebook_executes_exported_bytes_not_stored_outputs(tmp_path):
    source = tmp_path / "train.ipynb"
    source.write_text(
        json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": "cell-1",
                        "metadata": {},
                        "source": 'score = {"actual": 0.8}\n',
                        "execution_count": 99,
                        "outputs": [
                            {
                                "output_type": "stream",
                                "name": "stdout",
                                "text": "stored_notebook_secret",
                            }
                        ],
                    },
                ],
            }
        )
    )
    record = run_experiment(
        source, options=RunOptions(metrics=(parse_metric_binding("score=score"),))
    )
    assert record.run.status == "success"
    assert record.plan.subject.digest == sha256(source.read_bytes()).hexdigest()
    assert record.plan.subject.executable_digest != record.plan.subject.digest
    assert record.run.metrics[0].value == {"actual": 0.8}
    assert "stored_notebook_secret" not in record.model_dump_json()
    validate_run_binding(record.run, record.plan)
