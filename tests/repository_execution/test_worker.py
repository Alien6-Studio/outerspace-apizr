import sys

import pytest

from apizr.execution.policy import BackendCapabilities, ExecutionPolicy
from apizr.execution.serialization import digest
from apizr.interfaces.runtime import BindingError, IntegrityError
from apizr.repository_execution import worker
from apizr.repository_execution.model import Request
from apizr.repository_execution.supervisor import execute

from .helpers import planned
from .test_local import stage


@pytest.mark.parametrize(
    "source,status",
    [
        ("def run(): raise RuntimeError('SECRET')", "execution_failed"),
        ("def run(): return set()", "result_invalid"),
        ("def run(): return 'x'*2000", "output_limit"),
    ],
)
def test_worker_error_classification(tmp_path, source, status):
    plan, exposure, sources, _ = planned(
        source,
        policy=ExecutionPolicy.model_validate({"limits": {"max_output_bytes": 256}}),
    )
    stage(tmp_path, plan, exposure, sources)
    result = worker.handle(
        Request(plan=plan, plan_digest=digest(plan), arguments={}), tmp_path
    )
    assert result.status == status and result.value is None
    assert "sample.api" not in sys.modules


@pytest.mark.parametrize(
    "error,status",
    [
        (BindingError, "binding_failed"),
        (IntegrityError, "source_mismatch"),
        (RuntimeError, "execution_failed"),
    ],
)
def test_runtime_binding_failure(tmp_path, monkeypatch, error, status):
    plan, exposure, sources, _ = planned()
    stage(tmp_path, plan, exposure, sources)

    def fail(*args):
        raise error("private")

    monkeypatch.setattr(worker, "verify_binding", fail)
    assert (
        worker.handle(
            Request(plan=plan, plan_digest=digest(plan), arguments={}), tmp_path
        ).status
        == status
    )


def test_policy_and_interface_revalidation(tmp_path, monkeypatch):
    plan, exposure, sources, _ = planned()
    stage(tmp_path, plan, exposure, sources)
    request = Request(plan=plan, plan_digest=digest(plan), arguments={})
    monkeypatch.setattr(
        worker, "local_capabilities", lambda: BackendCapabilities(available=False)
    )
    assert worker.handle(request, tmp_path).status == "policy_refused"
    (tmp_path / "repository-interface.json").write_bytes(b"{}")
    assert worker.handle(request, tmp_path).status == "binding_failed"
    plan = plan.model_copy(update={"execution_context": "oci-container"})
    assert execute(plan, exposure, sources, {}).status == "policy_refused"


@pytest.mark.parametrize("valid", [True, False])
def test_framed_worker_main(tmp_path, monkeypatch, valid):
    import io
    import os
    from types import SimpleNamespace

    from apizr.execution.protocol import encode, frame, read_frame

    plan, exposure, sources, _ = planned()
    stage(tmp_path, plan, exposure, sources)
    request = Request(plan=plan, plan_digest=digest(plan), arguments={})
    data = frame(encode(request.model_dump(mode="json"), 1000000)) if valid else b"bad"
    output = tmp_path / "response"
    with output.open("wb"):
        monkeypatch.setattr(worker.os, "dup", lambda fd: os.open(output, os.O_WRONLY))
        monkeypatch.setattr(worker.os, "dup2", lambda *a: None)
        monkeypatch.setattr(
            worker.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(data))
        )
        monkeypatch.chdir(tmp_path)
        worker.main()
    with output.open("rb") as stream:
        result = read_frame(stream, 10000)
    assert result["status"] == ("success" if valid else "worker_failed")
