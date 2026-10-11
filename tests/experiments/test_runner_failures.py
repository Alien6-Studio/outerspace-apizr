"""No failed supervision or observation may fabricate success or lose a Run."""

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from apizr.execution.protocol import frame
from apizr.experiments import runner
from apizr.experiments.inspection import inspect_experiment
from apizr.experiments.model import EnvironmentEvidence
from apizr.experiments.planning import RunOptions, derive_plan
from apizr.experiments.run_protocol import WorkerFinished, WorkerStarted

from .test_worker_protocol import request


def setup(tmp_path):
    source = tmp_path / "train.py"
    source.write_text("value = 1")
    inspection = inspect_experiment(source)
    return source, inspection, derive_plan(inspection)


@pytest.mark.parametrize("failure", [OSError("PRIVATE"), KeyboardInterrupt()])
def test_supervision_failure_is_sanitized(tmp_path, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise failure

    if isinstance(failure, OSError):
        monkeypatch.setattr(runner.subprocess, "Popen", fail)
    else:
        monkeypatch.setattr(runner.selectors, "DefaultSelector", fail)
    result = runner._exchange(request(), tmp_path, RunOptions())
    assert result.status == ("failed" if isinstance(failure, OSError) else "cancelled")
    assert result.diagnostic == (
        "worker_failed" if isinstance(failure, OSError) else "execution_cancelled"
    )


def wire(message):
    return frame(message.model_dump_json().encode())


@pytest.mark.parametrize(
    "kind",
    [
        "incomplete",
        "extra",
        "invalid",
        "oversized",
        "parameter",
        "metric",
        "fragmented",
    ],
)
def test_private_protocol_refuses_malformed_and_unrequested_evidence(
    tmp_path, monkeypatch, kind
):
    started = wire(WorkerStarted(environment=EnvironmentEvidence()))
    finished = wire(WorkerFinished(status="success"))
    payload = started + finished
    if kind == "incomplete":
        payload = payload[:-1]
    elif kind == "extra":
        payload += finished
    elif kind == "invalid":
        payload = frame(b"not-json")
    elif kind == "oversized":
        monkeypatch.setattr(runner, "MAX_RESPONSE_BYTES", 8)
        payload = b"x" * 64
    elif kind in {"parameter", "metric"}:
        data = {
            "status": "success",
            ("parameters" if kind == "parameter" else "metrics"): [
                {"name": "unrequested", "value": 1, "origin": "runtime"}
            ],
        }
        payload = started + wire(WorkerFinished.model_validate_json(json.dumps(data)))
    real = subprocess.Popen
    processes = []
    script = "import os, sys, time\nsys.stdin.buffer.read()\n"
    if kind == "fragmented":
        script += f"os.write(1, {payload[:12]!r})\ntime.sleep(.08)\nos.write(1, {payload[12:]!r})\n"
    else:
        script += f"os.write(1, {payload!r})\n"

    def spawn(command, **kwargs):
        process = real([sys.executable, "-I", "-c", script], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(runner.subprocess, "Popen", spawn)
    result = runner._exchange(request(b"#" + b"x" * 100000), tmp_path, RunOptions())
    assert result.status == ("success" if kind == "fragmented" else "failed")
    assert all(
        p.stdin.closed and p.stdout.closed and p.poll() is not None for p in processes
    )


@pytest.mark.parametrize("failure", ["unsupported", "plan", "executable"])
def test_preflight_refusal(tmp_path, monkeypatch, failure):
    _, inspection, plan = setup(tmp_path)
    if failure == "unsupported":
        monkeypatch.setattr(runner, "os", SimpleNamespace(name="nt"))
        expected = "runner_requires_posix"
    elif failure == "plan":
        plan = plan.model_copy(
            update={
                "execution": plan.execution.model_copy(update={"kind": "other-intent"})
            }
        )
        expected = "plan_mismatch"
    else:
        # The byte/digest check is independent of the derivation check.
        altered = plan.model_copy(
            update={
                "subject": plan.subject.model_copy(
                    update={"executable_digest": "a" * 64}
                )
            }
        )
        with pytest.raises(ValueError, match="source_changed"):
            runner._source(inspection, altered, tmp_path)
        return
    with pytest.raises(ValueError, match=expected):
        runner.execute_plan(inspection, plan, root=tmp_path)


def test_cleanup_failure_is_recorded_not_success(tmp_path, monkeypatch):
    source, _, _ = setup(tmp_path)
    original = runner.kill_group

    def cleanup(process):
        original(process)
        raise OSError("private cleanup path")

    monkeypatch.setattr(runner, "kill_group", cleanup)
    record = runner.run_experiment(source)
    assert record.run.status == "failed"
    assert record.run.diagnostics[0].code == "worker_cleanup_failed"
    assert "private cleanup path" not in record.model_dump_json()


@pytest.mark.parametrize("failure", [OSError("private"), KeyboardInterrupt()])
def test_post_execution_capture_failure_persists(tmp_path, monkeypatch, failure):
    source, _, _ = setup(tmp_path)
    original = runner.fingerprint_inputs
    calls = 0

    def snapshot(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise failure
        return original(*args, **kwargs)

    monkeypatch.setattr(runner, "fingerprint_inputs", snapshot)
    record = runner.run_experiment(source)
    assert record.run.status == (
        "failed" if isinstance(failure, OSError) else "cancelled"
    )
    assert record.run.diagnostics[0].code == (
        "observation_failed" if isinstance(failure, OSError) else "execution_cancelled"
    )


def test_wall_clock_reversal_does_not_fabricate_order(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    source, _, _ = setup(tmp_path)
    instants = iter(
        [datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)]
    )
    monkeypatch.setattr(
        runner, "datetime", SimpleNamespace(now=lambda zone: next(instants))
    )
    record = runner.run_experiment(source)
    assert record.run.status == "failed"
    assert record.run.timing.ended_at is None
    assert record.run.timing.duration_seconds >= 0
    assert record.run.diagnostics[0].code == "clock_reversed"


def test_output_union_limit_is_preflight(tmp_path):
    from apizr.experiments.outputs import parse_output_declaration

    source, inspection, _ = setup(tmp_path)
    source.write_text('import joblib\njoblib.dump(None,"auto.bin")')
    inspection = inspect_experiment(source)
    options = RunOptions(
        outputs=tuple(parse_output_declaration(f"explicit{i}=o{i}") for i in range(256))
    )
    with pytest.raises(ValueError, match="output_selection_limit"):
        runner.execute_plan(
            inspection,
            derive_plan(inspection, execution=options),
            root=tmp_path,
            options=options,
        )
    assert not (tmp_path / "auto.bin").exists()
