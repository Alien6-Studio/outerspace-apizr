"""Canonical publication, context isolation and bounded explicit SDK observations."""

import asyncio
import importlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from apizr import tracking
from apizr.experiments import EvidenceOrigin, inputs, outputs, run_bytes, store
from apizr.experiments.comparison import compare_runs
from apizr.experiments.history import (
    history_bytes,
    list_runs,
    list_text,
    show_run,
    show_text,
)
from apizr.experiments.store import DEFAULT_STORE, RunRecordV2, records

implementation = importlib.import_module("apizr.tracking.session")


def test_explicit_evidence_and_terminal_publication(tmp_path):
    (tmp_path / "data.csv").write_bytes(b"value\n1\n")
    (tmp_path / "model.bin").write_bytes(b"model")
    (tmp_path / "train.py").write_text("x = 1\n")
    with tracking.session(root=tmp_path, source="train.py") as capture:
        tracking.log_parameter("rate", {"schedule": [0.1, 0.01]})
        tracking.log_metric("score", 0.75)
        tracking.log_input("training", "data.csv")
        tracking.log_input("memory")
        tracking.log_input("remote", uri="https://example.org/train.csv")
        tracking.log_artifact("model", "model.bin")
        record = capture.finalize()
        assert record is capture.finalize()
        with pytest.raises(tracking.TrackingError, match="tracking_session_closed"):
            tracking.log_metric("late", 1)
    assert isinstance(record, RunRecordV2)
    assert capture.record is record
    assert record.run.status == "success"
    assert record.run.subject.identity.reference == "train.py"
    assert record.run.observed_inputs[0].origin == EvidenceOrigin.UNKNOWN
    assert record.run.observed_inputs[1].content_origin == EvidenceOrigin.UNKNOWN
    assert record.run.observed_inputs[2].content_origin == EvidenceOrigin.RUNTIME
    assert record.plan.parameters == ()  # Observations are never retroactive intent.
    assert record.run.effective_parameters[0].origin == EvidenceOrigin.RUNTIME
    assert record.run.environment.python_version.origin == EvidenceOrigin.RUNTIME
    assert record.run.randomness == ()
    assert show_run(tmp_path / DEFAULT_STORE, record.run_digest) == record
    assert len(list(records(tmp_path / DEFAULT_STORE))) == 1
    assert "sdk_session" in show_text(record)
    listing = list_runs(tmp_path / DEFAULT_STORE)
    assert listing.schema_version == "apizr.experiment-history/v2"
    assert "rate" in list_text(listing) and "score=0.75" in list_text(listing)
    assert json.loads(history_bytes(record))["run_digest"] == record.run_digest


@pytest.mark.parametrize(
    "exception,status",
    [
        (RuntimeError("business-secret"), "failed"),
        (KeyboardInterrupt(), "cancelled"),
        (SystemExit(7), "failed"),
        (asyncio.CancelledError(), "cancelled"),
    ],
)
def test_business_exception_identity_is_preserved(tmp_path, exception, status):
    with pytest.raises(type(exception)) as caught:
        with tracking.session(root=tmp_path) as capture:
            tracking.log_metric("partial", 0.5)
            raise exception
    assert caught.value is exception
    assert capture.record.run.status == status
    assert capture.record.run.diagnostics
    assert b"business-secret" not in run_bytes(capture.record.run)
    with pytest.raises(tracking.TrackingError, match="tracking_no_active_session"):
        tracking.log_metric("outside", 1)


def test_publication_failure_never_masks_business_exception(tmp_path, monkeypatch):
    business = RuntimeError("business")

    def fail(*args):
        raise OSError("store-secret")

    monkeypatch.setattr(store, "publish", fail)
    with pytest.raises(RuntimeError) as caught:
        with tracking.session(root=tmp_path) as capture:
            raise business
    assert caught.value is business
    assert capture.record is None
    assert str(capture.publication_error) == "tracking_publication_failed"
    assert business.__notes__ == [
        "Apizr capture could not be published (tracking_publication_failed)."
    ]


def test_publication_failure_on_normal_exit_is_visible(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("unavailable")

    monkeypatch.setattr(store, "publish", fail)
    with pytest.raises(OSError, match="unavailable"):
        with tracking.session(root=tmp_path) as capture:
            pass
    assert capture.record is None
    with pytest.raises(tracking.TrackingError):
        capture.finalize()


@pytest.mark.parametrize("value", [object(), float("nan"), "x" * 8193, [object()]])
def test_invalid_parameter_is_never_pickled_or_successfully_published(tmp_path, value):
    with tracking.session(root=tmp_path) as capture:
        with pytest.raises(tracking.TrackingError, match="tracking_parameter_invalid"):
            tracking.log_parameter("parameter", value)
    assert capture.record.run.status == "failed"
    assert not capture.record.run.effective_parameters


@pytest.mark.parametrize(
    "method,args",
    [
        ("log_parameter", ("x", 1)),
        ("log_metric", ("x", 1)),
        ("log_input", ("x",)),
        ("log_artifact", ("x", "file.bin")),
    ],
)
def test_duplicate_names_are_refused_before_repeated_file_reads(
    tmp_path, method, args, monkeypatch
):
    (tmp_path / "file.bin").write_bytes(b"fixture")
    with tracking.session(root=tmp_path) as capture:
        getattr(capture, method)(*args)

        def forbidden(*args, **kwargs):
            raise AssertionError("duplicate re-read")

        monkeypatch.setattr(inputs, "fingerprint_input", forbidden)
        monkeypatch.setattr(outputs, "fingerprint_output", forbidden)
        with pytest.raises(tracking.TrackingError, match="tracking_duplicate_key"):
            getattr(capture, method)(*args)
    assert capture.record.run.status == "failed"


def test_counts_and_aggregate_bytes_are_bounded(tmp_path, monkeypatch):
    with tracking.session(root=tmp_path) as capture:
        for index in range(256):
            tracking.log_metric(f"metric{index}", index)
        with pytest.raises(tracking.TrackingError, match="tracking_count_limit"):
            tracking.log_metric("too-many", 1)
    assert len(capture.record.run.metrics) == 256
    assert capture.record.run.status == "failed"
    monkeypatch.setattr(implementation, "MAX_CAPTURE_BYTES", 200)
    with tracking.session(root=tmp_path) as capture:
        with pytest.raises(tracking.TrackingError, match="tracking_capture_limit"):
            tracking.log_parameter("large", "x" * 200)
    assert capture.record.run.status == "failed"


def test_nested_session_is_refused_and_recorded(tmp_path):
    with tracking.session(root=tmp_path) as capture:
        with pytest.raises(tracking.TrackingError, match="tracking_nested_session"):
            with tracking.session(root=tmp_path):
                pass
        tracking.log_metric("outer", 1)
    assert capture.record.run.status == "failed"
    assert len(list(records(tmp_path / DEFAULT_STORE))) == 1
    with pytest.raises(tracking.TrackingError, match="tracking_session_reused"):
        capture.__enter__()


def test_independent_thread_contexts_and_cross_thread_refusal(tmp_path):
    def capture(index):
        with tracking.session(root=tmp_path) as current:
            tracking.log_metric("thread", index)
        return current.record

    with ThreadPoolExecutor(max_workers=2) as pool:
        found = list(pool.map(capture, (1, 2)))
        with tracking.session(root=tmp_path) as parent:
            future = pool.submit(parent.log_metric, "foreign", 1)
            with pytest.raises(
                tracking.TrackingError, match="tracking_context_mismatch"
            ):
                future.result()
    assert sorted(record.run.metrics[0].value for record in found) == [1, 2]
    assert len(list(records(tmp_path / DEFAULT_STORE))) == 3


def test_async_tasks_do_not_write_to_inherited_parent_context(tmp_path):
    async def child(index):
        with pytest.raises(tracking.TrackingError, match="tracking_no_active_session"):
            tracking.log_metric("inherited", index)
        with tracking.session(root=tmp_path) as own:
            await asyncio.sleep(0)
            tracking.log_metric("task", index)
        return own.record

    async def run():
        with tracking.session(root=tmp_path) as parent:
            children = await asyncio.gather(child(1), child(2))
            tracking.log_metric("parent", 3)
        return parent.record, children

    parent, children = asyncio.run(run())
    assert parent.run.metrics[0].value == 3
    assert sorted(record.run.metrics[0].value for record in children) == [1, 2]
    assert len(list(records(tmp_path / DEFAULT_STORE))) == 3


@pytest.mark.parametrize(
    "reference", ["../outside", "/absolute", "missing.bin", "link.bin"]
)
def test_file_admission_reuses_core_boundaries(tmp_path, reference):
    (tmp_path / "target.bin").write_bytes(b"content")
    (tmp_path / "link.bin").symlink_to("target.bin")
    with tracking.session(root=tmp_path) as capture:
        with pytest.raises(tracking.TrackingError, match="tracking_artifact_invalid"):
            tracking.log_artifact("artifact", reference)
        with pytest.raises(tracking.TrackingError, match="tracking_input_invalid"):
            tracking.log_input("input", reference)
    assert capture.record.run.status == "failed"


def test_invalid_metric_and_non_string_name_are_sanitized(tmp_path):
    with tracking.session(root=tmp_path) as capture:
        with pytest.raises(tracking.TrackingError, match="tracking_metric_invalid"):
            tracking.log_metric("score", float("inf"))
        with pytest.raises(tracking.TrackingError, match="tracking_name_invalid"):
            tracking.log_parameter([], 1)
    assert capture.record.run.status == "failed"


def test_unknown_source_and_producer_agnostic_comparison(tmp_path):
    with tracking.session(root=tmp_path) as a:
        tracking.log_metric("score", 0.5)
    with tracking.session(root=tmp_path) as b:
        tracking.log_metric("score", 0.75)
    difference = compare_runs(a.record, b.record)
    assert difference.schema_version == "apizr.experiment-diff/v2"
    assert difference.source.state.value == "unknown"
    assert difference.metrics[0].delta == 0.25


def test_runner_suppression_is_inert_and_does_not_create_store(tmp_path, monkeypatch):
    monkeypatch.setenv("APIZR_EXPERIMENT_RUNNER", "1")
    tracking.log_metric("outside", object())
    with tracking.session(root=tmp_path) as capture:
        tracking.log_parameter("x", object())
        tracking.log_input("missing", "missing")
        tracking.log_artifact("missing", "missing")
        assert capture.finalize() is None
        assert capture.finalize() is None
    assert capture.record is None
    assert not (tmp_path / DEFAULT_STORE).exists()


def test_invalid_environment_selection_refuses_before_business_code(tmp_path):
    executed = False
    with pytest.raises(ValueError, match="environment_selection_invalid"):
        with tracking.session(root=tmp_path, distributions=("../invalid",)):
            executed = True
    assert not executed
    assert list(records(tmp_path / DEFAULT_STORE)) == []


def test_custom_task_equality_cannot_claim_parent_ownership(tmp_path):
    class EqualTask(asyncio.Task):
        def __eq__(self, other):
            return True

        __hash__ = object.__hash__

    async def run():
        with tracking.session(root=tmp_path) as parent:
            loop = asyncio.get_running_loop()
            loop.set_task_factory(
                lambda loop, coroutine, **kwargs: EqualTask(
                    coroutine, loop=loop, **kwargs
                )
            )
            try:

                async def child():
                    assert tracking.TrackingSession.current() is None
                    with pytest.raises(
                        tracking.TrackingError, match="tracking_context_mismatch"
                    ):
                        parent.log_metric("foreign", 1)

                await asyncio.create_task(child())
            finally:
                loop.set_task_factory(None)
        assert parent.record.run.metrics == ()

    asyncio.run(run())


def test_explicit_finalize_reports_publication_failure(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("unavailable")

    monkeypatch.setattr(store, "publish", fail)
    with tracking.session(root=tmp_path) as capture:
        with pytest.raises(OSError):
            capture.finalize()
        assert str(capture.publication_error) == "tracking_publication_failed"
    assert capture.record is None
