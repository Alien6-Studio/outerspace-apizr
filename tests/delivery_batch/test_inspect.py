"""Local batch inspection shares aggregate binding and never starts delivery."""

import json
import socket
from pathlib import Path
from threading import Event

import pytest
from batch_inputs import request
from delivery_batch.test_batch import Managed

from apizr.delivery_batch import (
    BatchError,
    deliver_batch,
    inspect_batch,
    operations,
)
from apizr.extension_runtime import CleanupFailed


def snapshot(root):
    return {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


def test_absent_status_is_typed_not_started_without_io_effects(tmp_path, monkeypatch):
    batch = request(tmp_path)
    monkeypatch.setattr(
        operations, "run_extension", lambda *a, **k: pytest.fail("plugin call")
    )
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("network call"))
    result = inspect_batch(batch)
    assert result.state == "failed" and result.exit_code == 1
    assert all(
        o.state == o.last_confirmed_stage == "not_started" and o.diagnostic is None
        for o in result.outcomes
    )
    assert not Path(batch.evidence_root).exists()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("partial", [False, True])
def test_status_is_exact_retained_result_without_mutation(
    tmp_path, monkeypatch, partial
):
    managed = Managed()
    batch = request(tmp_path)
    if partial:
        managed.fail = (
            "attest",
            batch.destinations[1].push.destination.rsplit(":", 1)[0],
        )
    monkeypatch.setattr(operations, "run_extension", managed)
    delivered = deliver_batch(batch)
    before = snapshot(tmp_path)
    monkeypatch.setattr(
        operations, "run_extension", lambda *a, **k: pytest.fail("plugin call")
    )
    assert inspect_batch(batch) == delivered
    assert snapshot(tmp_path) == before
    raw = delivered.model_dump_json()
    for private in [
        "/private/",
        str(tmp_path),
        "key_file",
        "trust_store",
        "authentication",
    ]:
        assert private not in raw


@pytest.mark.parametrize(
    "fault",
    [
        "build",
        "proof",
        "order",
        "extra",
        "duplicate",
        "oversized",
        "symlink",
        "directory",
        "root_symlink",
        "request",
    ],
)
def test_status_refuses_conflicting_or_redirected_evidence_without_mutation(
    tmp_path, monkeypatch, fault
):
    batch = request(tmp_path)
    root = Path(batch.evidence_root)
    root.mkdir()
    saved = root / "batch.json"
    initial = inspect_batch(batch)
    raw = initial.model_dump(mode="json", by_alias=True)
    if fault == "build":
        raw["build"]["image_id"] = "sha256:" + "f" * 64
    elif fault == "proof":
        raw["proof_requirement"] = "optional"
    elif fault == "order":
        raw["outcomes"].reverse()
    elif fault == "extra":
        raw["secret"] = "PRIVATE"
    saved.write_text(json.dumps(raw))
    if fault == "duplicate":
        saved.write_text(
            saved.read_text().replace(
                '"state": "failed"', '"state": "failed", "state": "failed"', 1
            )
        )
    elif fault == "oversized":
        saved.write_text("x" * 1048577)
    elif fault in {"symlink", "directory"}:
        saved.unlink()
        if fault == "symlink":
            target = tmp_path / "private"
            target.write_text(json.dumps(raw))
            saved.symlink_to(target)
        else:
            saved.mkdir()
    elif fault == "root_symlink":
        renamed = tmp_path / "other"
        root.rename(renamed)
        root.symlink_to(renamed)
    elif fault == "request":
        batch = batch.model_copy(update={"destinations": ()})
    before = snapshot(tmp_path)
    monkeypatch.setattr(
        operations, "run_extension", lambda *a, **k: pytest.fail("plugin call")
    )
    with pytest.raises(BatchError):
        inspect_batch(batch)
    assert snapshot(tmp_path) == before


def test_unconfirmed_cleanup_stops_batch_and_retains_uncertainty(tmp_path, monkeypatch):
    calls = []

    def unaccounted(*args, **kwargs):
        calls.append(args)
        raise CleanupFailed()

    monkeypatch.setattr(operations, "run_extension", unaccounted)
    batch = request(tmp_path)
    cancel = Event()
    with pytest.raises(CleanupFailed):
        deliver_batch(batch, cancel=cancel)
    assert cancel.is_set() and len(calls) == 1
    retained = inspect_batch(batch)
    assert retained.state == "cancelled"
    assert retained.outcomes[0].state == "remote_state_unconfirmed"
    assert all(o.state == "not_started" for o in retained.outcomes[1:])


def test_cancellation_waiting_for_batch_lock_preserves_confirmed_evidence(
    tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor

    from apizr.local_plugins.store import installation_lock

    batch = request(tmp_path)
    monkeypatch.setattr(operations, "run_extension", Managed())
    completed = deliver_batch(batch)
    cancel = Event()
    with installation_lock(Path(batch.evidence_root)):
        with ThreadPoolExecutor() as pool:
            future = pool.submit(deliver_batch, batch, resume=True, cancel=cancel)
            cancel.set()
            result = future.result(timeout=2)
    assert result.state == "cancelled" and result.outcomes == completed.outcomes
    assert inspect_batch(batch) == completed
