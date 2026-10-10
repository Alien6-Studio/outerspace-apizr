"""Canonical history fails closed, survives relocation and publishes exclusively."""

import json
import os
import shutil
import stat
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256

import pytest

from apizr.experiments import (
    EvidenceOrigin,
    ExperimentRun,
    RunDiagnostic,
    RunTiming,
    plan_bytes,
    plan_digest,
    run_bytes,
    run_digest,
    store,
)
from apizr.experiments.history import (
    HistoryList,
    HistoryQuery,
    history_bytes,
    list_runs,
    list_text,
    show_run,
    show_text,
    summary,
    summary_text,
)
from apizr.experiments.store import (
    RunRecord,
    StoreError,
    prepare_store,
    publish,
    records,
)


def test_exact_private_bytes_idempotence_and_relocation(tmp_path, pair):
    plan, run = pair
    root = tmp_path / "history"
    first = publish(root, plan, run)
    assert publish(root, plan, run) == first
    assert (root / "plans" / (plan_digest(plan) + ".json")).read_bytes() == plan_bytes(
        plan
    )
    assert (root / "runs" / (run_digest(run) + ".json")).read_bytes() == run_bytes(run)
    for path in [root, root / "plans", root / "runs"]:
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
    for path in root.rglob("*.json"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.stem == sha256(path.read_bytes()).hexdigest()
    moved = tmp_path / "moved"
    shutil.copytree(root, moved)
    assert show_run(moved, first.run_digest) == first
    assert show_run(moved, first.run_digest[:12]) == first
    assert first.run_digest in summary_text(summary(first))
    text = show_text(first)
    assert text.startswith("SUCCESS")
    assert all(
        section in text
        for section in [
            "Code",
            "Data",
            "Parameters",
            "Randomness",
            "Environment",
            "Metrics",
            "Outputs",
        ]
    )
    assert "agreement: yes" in text
    assert "runtime" in text
    assert RunRecord.model_validate_json(history_bytes(first)) == first


def test_absent_history_is_empty_without_writes(tmp_path):
    root = tmp_path / "absent" / "history"
    result = list_runs(root)
    assert result.total == result.matched == 0
    assert "0 shown" in list_text(result)
    assert not root.parent.exists()
    with pytest.raises(StoreError, match="run_not_found"):
        show_run(root, "a" * 64)


@pytest.mark.parametrize(
    "corruption",
    [
        "digest",
        "noncanonical",
        "invalid_json",
        "extra",
        "missing_plan",
        "plan_digest",
        "wrong_binding",
        "missing_runs",
        "filename",
        "directory",
        "fifo",
    ],
)
def test_corruption_not_hidden_by_filters_or_limits(tmp_path, pair, corruption):
    plan, run = pair
    record = publish(tmp_path, plan, run)
    path = tmp_path / "runs" / (record.run_digest + ".json")
    if corruption in {
        "digest",
        "noncanonical",
        "invalid_json",
        "extra",
        "wrong_binding",
    }:
        raw = path.read_bytes()
        data = json.loads(raw)
        if corruption == "digest":
            raw = raw.replace(b"success", b"failed")
        elif corruption == "noncanonical":
            raw = json.dumps(data, indent=2).encode()
        elif corruption == "invalid_json":
            raw = b"{"
        elif corruption == "extra":
            data["unknown"] = True
            raw = json.dumps(data).encode()
        else:
            data["subject"]["digest"] = "c" * 64
            raw = run_bytes(ExperimentRun.model_validate_json(json.dumps(data)))
        path.unlink()
        name = record.run_digest if corruption == "digest" else sha256(raw).hexdigest()
        (path.parent / (name + ".json")).write_bytes(raw)
    elif corruption == "missing_plan":
        next((tmp_path / "plans").iterdir()).unlink()
    elif corruption == "plan_digest":
        next((tmp_path / "plans").iterdir()).write_bytes(b"{}")
    elif corruption == "missing_runs":
        shutil.rmtree(tmp_path / "runs")
    elif corruption == "filename":
        path.rename(path.parent / "../escape.json")
        (tmp_path / "runs" / "bad-name").write_text("{}")
    elif corruption == "directory":
        path.unlink()
        path.mkdir()
    elif corruption == "fifo":
        path.unlink()
        os.mkfifo(path)
    before = {str(p): p.lstat().st_ino for p in tmp_path.rglob("*")}
    with pytest.raises(StoreError, match="store_corrupt"):
        list_runs(tmp_path, query=HistoryQuery(status="cancelled", limit=1))
    assert before == {str(p): p.lstat().st_ino for p in tmp_path.rglob("*")}
    with pytest.raises(StoreError, match="store_corrupt"):
        show_run(tmp_path, "f" * 64)


@pytest.mark.parametrize(
    "where", ["root", "ancestor", "plans", "runs", "plan", "run", "dangling"]
)
def test_symlinks_refused_for_read_and_write(tmp_path, pair, where):
    real = tmp_path / "real"
    record = publish(real, *pair)
    selected = real
    if where in {"root", "ancestor", "dangling"}:
        link = tmp_path / "link"
        link.symlink_to(
            tmp_path / "missing" if where == "dangling" else real,
            target_is_directory=True,
        )
        selected = link / "nested" if where == "ancestor" else link
    else:
        target = (
            real / where
            if where in {"plans", "runs"}
            else real
            / (where + "s")
            / ((record.plan_digest if where == "plan" else record.run_digest) + ".json")
        )
        backup = tmp_path / "outside"
        target.rename(backup)
        target.symlink_to(backup, target_is_directory=backup.is_dir())
    with pytest.raises(StoreError, match="store_corrupt"):
        list_runs(selected)
    with pytest.raises(StoreError, match="store_corrupt"):
        publish(selected, *pair)


def test_concurrent_idempotent_publication_has_one_complete_pair(tmp_path, pair):
    prepare_store(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        result = list(pool.map(lambda _: publish(tmp_path, *pair), range(16)))
    assert all(r == result[0] for r in result)
    assert len(list((tmp_path / "plans").iterdir())) == 1
    assert len(list((tmp_path / "runs").iterdir())) == 1
    assert list(records(tmp_path)) == [result[0]]


def changed_run(run, **changes):
    return ExperimentRun.model_validate(run.model_dump() | changes)


def test_ordering_exact_filters_and_json(tmp_path, pair):
    plan, original = pair
    records_ = []
    for status in ("success", "failed", "cancelled"):
        diagnostics = (
            ()
            if status == "success"
            else (RunDiagnostic(code="test_failure", origin=EvidenceOrigin.RUNTIME),)
        )
        run = changed_run(original, status=status, diagnostics=diagnostics)
        records_.append(publish(tmp_path, plan, run))
    untimed = changed_run(original, timing=None)
    records_.append(publish(tmp_path, plan, untimed))
    earlier = changed_run(
        original,
        timing=RunTiming(
            started_at=datetime(2025, 1, 1, tzinfo=UTC), origin=EvidenceOrigin.RUNTIME
        ),
    )
    records_.append(publish(tmp_path, plan, earlier))
    result = list_runs(tmp_path)
    assert [r.run_digest for r in result.runs[:3]] == sorted(
        r.run_digest for r in records_[:3]
    )
    assert result.runs[-1].started_at is None
    assert result.runs[-2].started_at.year == 2025
    assert "unknown" in list_text(result)
    assert HistoryList.model_validate_json(history_bytes(result)) == result
    assert list_runs(tmp_path, query=HistoryQuery(limit=1)).total == 5
    assert list_runs(tmp_path, query=HistoryQuery(status="failed")).matched == 1
    assert (
        list_runs(tmp_path, query=HistoryQuery(source=plan.subject.reference)).matched
        == 5
    )
    assert list_runs(tmp_path, query=HistoryQuery(source="elsewhere.py")).matched == 0
    assert (
        list_runs(
            tmp_path, query=HistoryQuery(capability="python:train:predict")
        ).matched
        == 0
    )
    for record in records_[1:3]:
        assert record.run.status.upper() in show_text(record)
        assert "test_failure" in show_text(record)


@pytest.mark.parametrize("run_id", ["x", "a" * 11, "a" * 65, "A" * 64, "../etc/passwd"])
def test_invalid_ids_never_traverse(tmp_path, run_id):
    with pytest.raises(StoreError, match="run_id_invalid"):
        show_run(tmp_path, run_id)


def test_orphan_plan_and_interrupted_stage_are_not_runs(tmp_path, pair):
    prepare_store(tmp_path)
    plan = pair[0]
    (tmp_path / "plans" / (plan_digest(plan) + ".json")).write_bytes(plan_bytes(plan))
    (tmp_path / "runs" / (".stage-" + "a" * 32)).symlink_to(tmp_path / "missing")
    assert list_runs(tmp_path).total == 0
    assert len(list((tmp_path / "runs").iterdir())) == 1


@pytest.mark.parametrize("limit", ["entries", "file", "total"])
def test_store_resource_bounds(tmp_path, pair, monkeypatch, limit):
    publish(tmp_path, *pair)
    monkeypatch.setattr(
        store,
        {
            "entries": "MAX_ENTRIES",
            "file": "MAX_ARTIFACT_BYTES",
            "total": "MAX_READ_BYTES",
        }[limit],
        0,
    )
    with pytest.raises(
        StoreError, match="store_corrupt" if limit == "file" else "store_limit"
    ):
        list_runs(tmp_path)


def test_wrong_binding_cannot_publish_anything(tmp_path, pair):
    plan, run = pair
    bad = changed_run(run, plan_digest="a" * 64)
    root = tmp_path / "history"
    with pytest.raises(StoreError, match="store_publish_failed"):
        publish(root, plan, bad)
    assert not root.exists()


def test_existing_corrupt_bytes_never_replaced(tmp_path, pair):
    record = publish(tmp_path, *pair)
    path = tmp_path / "runs" / (record.run_digest + ".json")
    path.write_bytes(b"corrupt")
    with pytest.raises(StoreError, match="store_corrupt"):
        publish(tmp_path, *pair)
    assert path.read_bytes() == b"corrupt"


def test_record_envelope_cannot_lie_about_digests(pair):
    plan, run = pair
    with pytest.raises(ValueError, match="store_digest_mismatch"):
        RunRecord(
            plan=plan, run=run, plan_digest=plan_digest(plan), run_digest="a" * 64
        )


def test_growing_file_is_bounded_even_after_fstat(tmp_path, monkeypatch):
    path = tmp_path / "growing"
    path.write_bytes(b"a")
    original = store.os.read

    def grow(fd, count):
        path.write_bytes(b"abc")
        return original(fd, count)

    monkeypatch.setattr(store, "MAX_ARTIFACT_BYTES", 2)
    monkeypatch.setattr(store.os, "read", grow)
    with store._root(tmp_path, create=False) as directory:
        with pytest.raises(StoreError, match="store_corrupt"):
            store._read(directory, "growing")


@pytest.mark.parametrize("failure", ["zero_write", "conflict", "full"])
def test_exclusive_publication_failures_leave_original_and_no_stage(
    tmp_path, monkeypatch, failure
):
    name = "a" * 64 + ".json"
    (tmp_path / name).write_bytes(b"original")
    if failure == "zero_write":
        monkeypatch.setattr(store.os, "write", lambda *args: 0)
    elif failure == "full":
        monkeypatch.setattr(store, "MAX_ENTRIES", 1)
    with store._root(tmp_path, create=False) as directory:
        with pytest.raises((OSError, StoreError)):
            store._publish(
                directory, ("b" * 64 + ".json") if failure == "full" else name, b"new"
            )
    assert (tmp_path / name).read_bytes() == b"original"
    assert len(list(tmp_path.iterdir())) == 1


def test_noncanonical_plan_refused(tmp_path, pair):
    prepare_store(tmp_path)
    data = json.dumps(pair[0].model_dump(mode="json"), indent=2).encode()
    (tmp_path / "plans" / (sha256(data).hexdigest() + ".json")).write_bytes(data)
    with pytest.raises(StoreError, match="store_corrupt"):
        list_runs(tmp_path)


def test_concurrent_new_plan_respects_reader_budget(tmp_path, pair, monkeypatch):
    record = publish(tmp_path, *pair)
    names = store._names
    calls = 0

    def inventory(directory):
        nonlocal calls
        calls += 1
        return () if calls == 1 else names(directory)

    # Simulate Plan+Run published after the Plan inventory. Load on demand, still
    # bounded: a concurrent canonical Run cannot introduce unlimited Plan reads.
    monkeypatch.setattr(store, "_names", inventory)
    assert list(records(tmp_path)) == [record]
    calls = 0
    monkeypatch.setattr(store, "MAX_ENTRIES", 0)
    monkeypatch.setattr(
        store,
        "_names",
        lambda directory: (
            ()
            if os.fstat(directory).st_ino == (tmp_path / "plans").stat().st_ino
            else (record.run_digest + ".json",)
        ),
    )
    with pytest.raises(StoreError, match="store_limit"):
        list_runs(tmp_path)


def test_history_envelope_invariants_and_ambiguous_prefix(tmp_path, pair, monkeypatch):
    from apizr.experiments import history

    record = publish(tmp_path, *pair)
    brief = summary(record)
    with pytest.raises(ValueError, match="history_counts_invalid"):
        HistoryList(query=HistoryQuery(), total=0, matched=0, runs=(brief,))
    with pytest.raises(ValueError, match="history_duplicate_run"):
        HistoryList(query=HistoryQuery(), total=2, matched=2, runs=(brief, brief))
    other = brief.model_copy(
        update={"run_digest": "a" * 64 if brief.run_digest != "a" * 64 else "b" * 64}
    )
    unsorted = tuple(sorted((brief, other), key=lambda r: r.run_digest, reverse=True))
    with pytest.raises(ValueError, match="history_order_invalid"):
        HistoryList(query=HistoryQuery(), total=2, matched=2, runs=unsorted)
    monkeypatch.setattr(history, "records", lambda path: iter([record, record]))
    with pytest.raises(StoreError, match="run_id_ambiguous"):
        show_run(tmp_path, record.run_digest[:12])


def test_empty_observed_sections_are_explicit(tmp_path, pair):
    plan, original = pair
    run = changed_run(
        original,
        environment=None,
        metrics=(),
        outputs=(),
        randomness=(),
        timing=None,
        observed_inputs=(),
    )
    record = publish(tmp_path, plan, run)
    text = show_text(record)
    assert "Worker environment not observed" in text
    assert "runtime application not directly observed" in text
    assert "No runtime metric" in text and "No runtime output" in text
    assert "content unknown; agreement: not established" in text
    with pytest.raises(StoreError, match="run_not_found"):
        show_run(tmp_path, "f" * 64)


def test_reviewed_history_fixtures_and_additive_schemas():
    from pathlib import Path

    from jsonschema import Draft202012Validator

    from apizr.experiments.history import RunSummary

    root = Path(__file__).resolve().parents[2]
    fixtures = root / "tests/fixtures/experiments/history/v1"
    listing = list_runs(fixtures)
    assert {r.status for r in listing.runs} == {"success", "failed", "cancelled"}
    values = [listing, *records(fixtures)]
    for record in records(fixtures):
        values.append(summary(record))
    for name, model in [
        ("history", HistoryList),
        ("record", RunRecord),
        ("run-result", RunSummary),
    ]:
        schema = json.loads(
            (root / f"docs/specs/apizr-experiment-{name}-v1.schema.json").read_bytes()
        )
        assert schema == model.model_json_schema()
        Draft202012Validator.check_schema(schema)
        for value in values:
            if isinstance(value, model):
                Draft202012Validator(schema).validate(value.model_dump(mode="json"))


def test_orphan_plan_digest_refused(tmp_path, pair):
    prepare_store(tmp_path)
    (tmp_path / "plans" / ("a" * 64 + ".json")).write_bytes(plan_bytes(pair[0]))
    with pytest.raises(StoreError, match="store_corrupt"):
        list_runs(tmp_path)


def test_minimal_history_does_not_invent_executable_digest(tmp_path, pair):
    from apizr.experiments import ExperimentPlan

    plan, run = pair
    subject = plan.subject.model_copy(update={"executable_digest": None})
    plan = ExperimentPlan.model_validate(plan.model_dump() | {"subject": subject})
    run = changed_run(run, subject=subject, plan_digest=plan_digest(plan))
    assert "Executable sha256" not in show_text(publish(tmp_path, plan, run))


@pytest.mark.parametrize("missing", ["plans", "runs"])
def test_existing_partial_store_is_never_reinitialized(tmp_path, pair, missing):
    publish(tmp_path, *pair)
    shutil.rmtree(tmp_path / missing)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    with pytest.raises(StoreError, match="store_corrupt"):
        publish(tmp_path, *pair)
    assert not (tmp_path / missing).exists()
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}


def test_distinct_processes_converge_on_first_plan_and_keep_both_runs(tmp_path, pair):
    import subprocess
    import sys
    from contextlib import ExitStack

    plan, run = pair
    other = changed_run(run, timing=None)
    (tmp_path / "plan.json").write_bytes(plan_bytes(plan))
    for number, value in enumerate((run, other)):
        (tmp_path / f"run{number}.json").write_bytes(run_bytes(value))
    code = """import sys
from pathlib import Path
from apizr.experiments import ExperimentPlan,ExperimentRun
from apizr.experiments.store import publish
root=Path(sys.argv[1])
plan=ExperimentPlan.model_validate_json((root/'plan.json').read_bytes())
run=ExperimentRun.model_validate_json((root/f'run{sys.argv[2]}.json').read_bytes())
publish(root/'new-store',plan,run)
"""
    with ExitStack() as stack:
        processes = [
            stack.enter_context(
                subprocess.Popen(
                    [sys.executable, "-I", "-B", "-c", code, str(tmp_path), str(i % 2)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            )
            for i in range(8)
        ]
        try:
            for process in processes:
                output, error = process.communicate(timeout=15)
                assert process.returncode == 0, (output, error)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)
    assert len(list((tmp_path / "new-store/plans").iterdir())) == 1
    result = list_runs(tmp_path / "new-store")
    assert {r.run_digest for r in result.runs} == {run_digest(run), run_digest(other)}


def test_initialization_race_with_existing_directory_is_safe(tmp_path, monkeypatch):
    original = store.os.mkdir

    def another_writer(name, *args, **kwargs):
        if name == "plans" and "dir_fd" in kwargs:
            original(name, *args, **kwargs)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(store.os, "mkdir", another_writer)
    prepare_store(tmp_path)
    assert list_runs(tmp_path).total == 0
