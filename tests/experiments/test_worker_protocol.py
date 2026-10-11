"""Strict workload messages and runtime binding observations, without coercion."""

import base64
import io
import json
import sys
from hashlib import sha256
from types import SimpleNamespace

import pytest

from apizr.experiments import (
    EnvironmentEvidence,
    EnvironmentValue,
    EvidenceOrigin,
    SourceIdentity,
    worker,
)
from apizr.experiments.planning import parse_metric_binding
from apizr.experiments.run_protocol import (
    WorkerFinished,
    WorkerStarted,
    WorkloadRequest,
)


def request(source=b"pass", **kw):
    return WorkloadRequest(
        subject=SourceIdentity(
            kind="python",
            reference="train.py",
            module="train",
            digest=sha256(source).hexdigest(),
            executable_digest=sha256(source).hexdigest(),
        ),
        plan_digest="a" * 64,
        original=base64.b64encode(source).decode(),
        executable=base64.b64encode(source).decode(),
        **kw,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"original": "!"},
        {"executable": "!"},
        {"original": "YQ=="},
        {"executable": "YQ=="},
        {"parameters": ["a", "a"]},
        {"parameters": ["a"] * 257},
        {
            "required_metrics": [
                {"name": "a", "binding": "x"},
                {"name": "a", "binding": "y"},
            ]
        },
        {
            "automatic_metrics": [
                {"name": "a", "binding": "x"},
                {"name": "a", "binding": "y"},
            ]
        },
        {"unknown": 1},
        {"schema_version": "future"},
    ],
)
def test_forged_requests_refused(change):
    data = request().model_dump(mode="json") | change
    with pytest.raises(ValueError):
        WorkloadRequest.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("kind", ["python", "notebook"])
def test_request_byte_bounds(kind):
    raw = b"x" * (1024**2 + 1 if kind == "python" else 16 * 1024**2 + 1)
    small = b"pass"
    with pytest.raises(ValueError, match="source_changed"):
        WorkloadRequest(
            subject=SourceIdentity(
                kind=kind,
                reference="train.py",
                digest=sha256(raw).hexdigest(),
                executable_digest=sha256(small).hexdigest(),
            ),
            plan_digest="a" * 64,
            original=base64.b64encode(raw).decode(),
            executable=base64.b64encode(small).decode(),
        )


def test_python_cannot_substitute_different_executable():
    data = request().model_dump(mode="json")
    data["executable"] = base64.b64encode(b"other").decode()
    data["subject"]["executable_digest"] = sha256(b"other").hexdigest()
    with pytest.raises(ValueError, match="source_changed"):
        WorkloadRequest.model_validate_json(json.dumps(data))


def test_started_cannot_promote_static_environment():
    with pytest.raises(ValueError, match="worker_environment_not_runtime"):
        WorkerStarted(
            environment=EnvironmentEvidence(
                python_version=EnvironmentValue(
                    value="3.12", origin=EvidenceOrigin.STATIC
                )
            )
        )
    assert WorkerStarted(environment=EnvironmentEvidence()).phase == "started"


@pytest.mark.parametrize(
    "change,code",
    [
        (
            {"parameters": [{"name": "x", "value": 1, "origin": "static"}]},
            "worker_parameter_not_runtime",
        ),
        ({"diagnostic": "execution_exception"}, "worker_status_diagnostic"),
        ({"status": "failed"}, "worker_status_diagnostic"),
        (
            {
                "status": "failed",
                "diagnostic": "execution_exit",
                "parameters": [{"name": "x", "value": 1, "origin": "runtime"}],
            },
            "worker_failed_observations",
        ),
        (
            {"parameters": [{"name": "x", "value": 1, "origin": "runtime"}] * 2},
            "worker_duplicate_observation",
        ),
        (
            {"metrics": [{"name": "x", "value": 1, "origin": "runtime"}] * 2},
            "worker_duplicate_observation",
        ),
    ],
)
def test_finished_semantic_validation(change, code):
    with pytest.raises(ValueError, match=code):
        WorkerFinished.model_validate_json(json.dumps({"status": "success"} | change))


def test_observe_unsupported_objects_not_coerced_and_explicit_wins():
    class Hostile:
        def __repr__(self):
            pytest.fail("repr executed")

    req = request(
        parameters=("valid", "bad", "missing"),
        automatic_metrics=(
            parse_metric_binding("score=bad"),
            parse_metric_binding("auto=valid"),
            parse_metric_binding("missing=missing"),
            parse_metric_binding("bad=bad"),
        ),
        required_metrics=(parse_metric_binding("score=valid"),),
    )
    result = worker.observe(req, {"valid": {"x": [1, None]}, "bad": Hostile()})
    assert result.status == "success"
    assert [p.name for p in result.parameters] == ["valid"]
    assert {m.name for m in result.metrics} == {"score", "auto"}


@pytest.mark.parametrize("value", [object(), float("inf")])
def test_required_invalid_fails_capture(value):
    result = worker.observe(
        request(required_metrics=(parse_metric_binding("score=value"),)),
        {"value": value},
    )
    assert result.diagnostic == "metric_capture_failed"


def test_observation_budget_prioritizes_required_metrics(monkeypatch):
    monkeypatch.setattr(worker, "MAX_CAPTURE_BYTES", 128)
    req = request(
        parameters=("a", "b", "c"),
        required_metrics=(parse_metric_binding("required=a"),),
        automatic_metrics=(parse_metric_binding("auto=a"),),
    )
    result = worker.observe(req, dict.fromkeys(["a", "b", "c"], 1))
    assert result.status == "success"
    assert [m.name for m in result.metrics] == ["required"]
    assert len(result.parameters) == 1
    required = request(
        required_metrics=tuple(
            parse_metric_binding(f"{n}={n}") for n in ["a", "b", "c"]
        )
    )
    assert (
        worker.observe(required, dict.fromkeys(["a", "b", "c"], 1)).diagnostic
        == "metric_capture_failed"
    )


def test_auto_metric_union_is_bounded():
    req = request(
        required_metrics=tuple(parse_metric_binding(f"m{i}=value") for i in range(256)),
        automatic_metrics=(parse_metric_binding("auto=value"),),
    )
    result = worker.observe(req, {"value": 1})
    assert result.status == "success" and len(result.metrics) == 256


@pytest.mark.parametrize(
    "body,status,code",
    [
        ("score = 1", "success", None),
        ("raise SystemExit()", "success", None),
        ("raise SystemExit(0)", "success", None),
        ("raise SystemExit(2)", "failed", "execution_exit"),
        ('raise ValueError("SECRET")', "failed", "execution_exception"),
        ("raise KeyboardInterrupt", "cancelled", "execution_cancelled"),
    ],
)
def test_execute_namespace_and_outcomes(tmp_path, monkeypatch, body, status, code):
    req = request(body.encode())
    (tmp_path / "train.py").write_text(body)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    monkeypatch.setitem(sys.modules, "__main__", sys.modules["__main__"])
    started = []
    result = worker.execute(req, started.append)
    assert result.status == status and result.diagnostic == code
    assert len(started) == 1
    assert started[0].environment.python_version.origin == EvidenceOrigin.RUNTIME
    assert sys.modules["__main__"].__file__ == "train.py"
    assert sys.path[0] == str(tmp_path)
    assert sys.argv == ["train.py"]


@pytest.mark.parametrize("missing", [False, True])
def test_worker_rechecks_source_before_exec(tmp_path, monkeypatch, missing):
    monkeypatch.chdir(tmp_path)
    req = request(b'raise AssertionError("executed")')
    if not missing:
        (tmp_path / "train.py").write_text("changed")
    assert worker.execute(req, lambda event: None).diagnostic == "source_changed"


def test_worker_rechecks_known_input(tmp_path, monkeypatch):
    from apizr.experiments.inputs import fingerprint_inputs, parse_input_declaration

    monkeypatch.chdir(tmp_path)
    (tmp_path / "train.py").write_text("pass")
    (tmp_path / "data").write_text("before")
    inputs = fingerprint_inputs(
        tmp_path, (parse_input_declaration("data=data"),)
    ).artifacts
    req = request(inputs=inputs)
    (tmp_path / "data").write_text("after")
    assert worker.execute(req, lambda event: None).diagnostic == "input_changed"


@pytest.mark.parametrize("invalid", [False, True])
def test_worker_main_private_descriptor_and_bounded_frames(monkeypatch, invalid):
    from apizr.execution.protocol import frame, size

    req = request()
    raw = b"invalid" if invalid else req.model_dump_json().encode()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(frame(raw))))

    class Output(io.BytesIO):
        def __exit__(self, *args):
            return False

    output = Output()
    calls = []
    monkeypatch.setattr(worker.os, "dup", lambda fd: calls.append(("dup", fd)) or 12)
    monkeypatch.setattr(worker.os, "dup2", lambda a, b: calls.append(("dup2", a, b)))
    monkeypatch.setattr(worker.os, "fdopen", lambda fd, mode: output)

    def execute(req, send):
        send(WorkerStarted(environment=EnvironmentEvidence()))
        return WorkerFinished(status="success")

    monkeypatch.setattr(worker, "execute", execute)
    worker.main()
    assert calls == [("dup", 1), ("dup2", 2, 1)]
    data = output.getvalue()
    length = size(data[:8], 2 * 1024**2)
    if invalid:
        assert (
            WorkerFinished.model_validate_json(data[8 : 8 + length]).diagnostic
            == "worker_failed"
        )
    else:
        assert (
            WorkerStarted.model_validate_json(data[8 : 8 + length]).environment
            == EnvironmentEvidence()
        )
        assert (
            WorkerFinished.model_validate_json(data[16 + length :]).status == "success"
        )


def test_module_entrypoint_executes_and_frames_exact_request(tmp_path, monkeypatch):
    import runpy

    body = b"value = 7"
    (tmp_path / "train.py").write_bytes(body)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    monkeypatch.setitem(sys.modules, "__main__", sys.modules["__main__"])
    from apizr.execution.protocol import frame, size

    monkeypatch.setattr(
        sys,
        "stdin",
        SimpleNamespace(
            buffer=io.BytesIO(frame(request(body).model_dump_json().encode()))
        ),
    )

    class Output(io.BytesIO):
        def __exit__(self, *args):
            return False

    output = Output()
    fdopen = worker.os.fdopen
    monkeypatch.setattr(worker.os, "dup", lambda fd: 10000)
    monkeypatch.setattr(worker.os, "dup2", lambda *args: None)
    monkeypatch.setattr(
        worker.os,
        "fdopen",
        lambda fd, *args: output if fd == 10000 else fdopen(fd, *args),
    )
    runpy.run_path(worker.__file__, run_name="__main__")
    raw = output.getvalue()
    first = size(raw[:8], 2 * 1024**2)
    assert WorkerStarted.model_validate_json(raw[8 : 8 + first]).phase == "started"
    assert WorkerFinished.model_validate_json(raw[16 + first :]).status == "success"
