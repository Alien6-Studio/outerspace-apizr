"""Kernel observations are bounded, context-bound and independent of saved files."""

import builtins
import hashlib
from types import SimpleNamespace

import pytest

from apizr import tracking
from apizr.experiments import CaptureMode, EvidenceOrigin
from apizr.experiments.store import DEFAULT_STORE
from apizr.tracking.kernel import MAX_CELL_BYTES


def shell(monkeypatch, *, count=1, code="pass", metadata=None, parent=None):
    message = (
        parent
        if parent is not None
        else {
            "header": {"msg_type": "execute_request"},
            "content": {"code": code},
            "metadata": {} if metadata is None else metadata,
        }
    )
    value = SimpleNamespace(
        displayhook=SimpleNamespace(prompt_count=count),
        kernel=SimpleNamespace(get_parent=lambda channel: message),
    )
    monkeypatch.setattr(builtins, "get_ipython", lambda: value, raising=False)
    return value


def test_observation_is_at_entry_not_session_construction(monkeypatch, tmp_path):
    value = shell(monkeypatch, count=1, code="old")
    capture = tracking.session(root=tmp_path)
    value.displayhook.prompt_count = 2
    source = "print('current cell — observed, not retained')"
    value.kernel.get_parent = lambda channel: {
        "header": {"msg_type": "execute_request"},
        "content": {"code": source},
        "metadata": {"cellId": "frontend-cell"},
    }
    with capture:
        tracking.log_input("already-in-memory")
    run = capture.record.run
    assert run.capture.mode == CaptureMode.JUPYTER_CELL
    assert run.capture.cell.execution_count == 2
    assert run.capture.cell.cell_id == "frontend-cell"
    assert run.capture.cell.source_digest == hashlib.sha256(source.encode()).hexdigest()
    assert run.subject.identity is None
    assert run.observed_inputs[0].origin == EvidenceOrigin.UNKNOWN
    assert "observed, not retained" not in capture.record.model_dump_json()


@pytest.mark.parametrize(
    "value", [None, SimpleNamespace(), SimpleNamespace(kernel=None)]
)
def test_non_kernel_shell_has_unknown_cell(monkeypatch, tmp_path, value):
    monkeypatch.setattr(builtins, "get_ipython", lambda: value, raising=False)
    with tracking.session(root=tmp_path) as capture:
        pass
    assert capture.record.run.capture.mode == CaptureMode.SDK_SESSION
    assert capture.record.run.capture.cell.origin == EvidenceOrigin.UNKNOWN


@pytest.mark.parametrize(
    "parent",
    [
        {},
        {"header": {"msg_type": "kernel_info_request"}},
        {"header": {"msg_type": "complete_request"}, "content": {"code": "pass"}},
    ],
    ids=["no_request", "kernel_info", "completion"],
)
def test_non_execution_request_is_not_presented_as_a_cell(
    monkeypatch, tmp_path, parent
):
    shell(monkeypatch, parent=parent)
    with tracking.session(root=tmp_path) as capture:
        pass
    assert capture.record.run.capture.cell.origin == EvidenceOrigin.UNKNOWN


@pytest.mark.parametrize(
    "changes",
    [
        {"code": object()},
        {"code": "x" * (MAX_CELL_BYTES + 1)},
        {"code": "é" * (MAX_CELL_BYTES // 2 + 1)},
        {"code": "\ud800"},
        {"count": True},
        {"count": -1},
        {"count": 2**63},
        {"metadata": []},
        {"metadata": {"cellId": "private-cell-id\n"}},
        {"parent": []},
        {"parent": {"header": {"msg_type": "execute_request"}, "content": []}},
    ],
)
def test_invalid_observations_refuse_before_business_code_or_store(
    monkeypatch, tmp_path, changes
):
    shell(monkeypatch, **changes)
    with pytest.raises(
        tracking.TrackingError, match="^tracking_kernel_observation_invalid$"
    ):
        with tracking.session(root=tmp_path):
            raise AssertionError("business code must not run")
    assert not (tmp_path / DEFAULT_STORE).exists()


def test_suppressed_capture_does_not_call_kernel_accessor(monkeypatch, tmp_path):
    def forbidden():
        raise AssertionError("kernel accessor must stay untouched")

    monkeypatch.setattr(builtins, "get_ipython", forbidden, raising=False)
    monkeypatch.setenv("APIZR_SERVED_PROCESS", "1")
    with tracking.session(root=tmp_path) as capture:
        tracking.log_metric("result", 1)
    assert capture.record is None
    assert not (tmp_path / DEFAULT_STORE).exists()


def test_no_counter_increment_is_not_fabricated(monkeypatch, tmp_path):
    shell(monkeypatch, count=0)
    with tracking.session(root=tmp_path) as capture:
        pass
    assert capture.record.run.capture.cell.execution_count is None
    assert capture.record.run.capture.cell.origin == EvidenceOrigin.RUNTIME
