"""Single-pass reads preserve full admission, canonical output and public refusals."""

from hashlib import sha256
from pathlib import Path

import pytest

from apizr.experiments import history, serialization, store
from apizr.experiments.comparison import compare_runs, compare_stored_runs, diff_bytes
from apizr.experiments.history import (
    history_bytes,
    list_runs,
    select_runs,
    show_run,
    summary,
)
from apizr.experiments.model import EvidenceOrigin, ExperimentRun, Metric
from apizr.experiments.store import StoreError, publish, records, validate_record


def test_reader_validates_each_canonical_artifact_once_without_revalidation(
    tmp_path, pair, monkeypatch
):
    first = publish(tmp_path, *pair)
    plan, run = pair
    second = publish(
        tmp_path,
        plan,
        ExperimentRun.model_validate(run.model_dump() | {"timing": None}),
    )
    reads = {"plan": 0, "run": 0}
    for key in ("plan", "run"):
        original = getattr(store, "read_" + key)

        def observed(data, key=key, original=original):
            reads[key] += 1
            return original(data)

        monkeypatch.setattr(store, "read_" + key, observed)

    def duplicate(*args, **kwargs):
        raise AssertionError("Store reads must reuse already admitted artifacts")

    for name in (
        "plan_bytes",
        "run_bytes",
        "plan_digest",
        "run_digest",
        "validate_record",
    ):
        monkeypatch.setattr(store, name, duplicate)
    monkeypatch.setattr(history, "validate_record", duplicate)
    result = list_runs(tmp_path)
    assert {r.run_digest for r in result.runs} == {first.run_digest, second.run_digest}
    assert reads == {"plan": 1, "run": 2}


def test_stored_diff_matches_reviewed_bytes(tmp_path):
    fixture = Path(__file__).resolve().parents[1] / "fixtures/experiments/comparison/v1"
    a = store.RunRecord.model_validate_json((fixture / "a.record.json").read_bytes())
    b = store.RunRecord.model_validate_json((fixture / "b.record.json").read_bytes())
    for record in (a, b):
        publish(tmp_path, record.plan, record.run)
    assert (
        diff_bytes(compare_stored_runs(tmp_path, a.run_digest, b.run_digest))
        == (fixture / "diff.json").read_bytes()
    )


@pytest.mark.parametrize(
    "ids", [(), ("a" * 64,) * 3, ("invalid",), ("a" * 64, "../secret")]
)
def test_invalid_selections_refused_before_any_io(tmp_path, monkeypatch, ids):
    def denied(*args):
        raise AssertionError("Invalid selection reached store")

    monkeypatch.setattr(history, "records", denied)
    with pytest.raises(StoreError, match="run_id_invalid"):
        select_runs(tmp_path, ids)


def test_select_pair_reports_errors_in_argument_order_after_global_validation(
    tmp_path, pair, monkeypatch
):
    record = publish(tmp_path, *pair)
    monkeypatch.setattr(history, "records", lambda path: iter([record, record]))
    with pytest.raises(StoreError, match="run_not_found"):
        select_runs(tmp_path, ("f" * 64, record.run_digest))
    with pytest.raises(StoreError, match="run_id_ambiguous"):
        select_runs(tmp_path, (record.run_digest, "f" * 64))


def test_both_selected_runs_do_not_hide_corruption_or_later_changes(tmp_path, pair):
    record = publish(tmp_path, *pair)
    expected = diff_bytes(compare_runs(record, record))
    assert (
        diff_bytes(
            compare_stored_runs(tmp_path, record.run_digest, record.run_digest[:12])
        )
        == expected
    )
    broken = tmp_path / "runs" / ("f" * 64 + ".json")
    broken.write_bytes(b"not a valid run")
    with pytest.raises(StoreError, match="store_corrupt"):
        compare_stored_runs(tmp_path, record.run_digest, record.run_digest)
    broken.unlink()
    assert (
        diff_bytes(compare_stored_runs(tmp_path, record.run_digest, record.run_digest))
        == expected
    )
    (tmp_path / "plans" / (record.plan_digest + ".json")).write_bytes(b"{}")
    with pytest.raises(StoreError, match="store_corrupt"):
        compare_stored_runs(tmp_path, record.run_digest, record.run_digest)


def test_public_record_consumers_still_revalidate_forged_values(tmp_path, pair):
    record = publish(tmp_path, *pair)
    read = show_run(tmp_path, record.run_digest)
    assert history_bytes(read) == history_bytes(record)
    forged = read.model_copy(update={"run_digest": "a" * 64})
    for operation in (
        validate_record,
        summary,
        history_bytes,
        lambda value: compare_runs(value, read),
    ):
        with pytest.raises(ValueError, match="store_digest_mismatch"):
            operation(forged)


def test_reader_binding_checked_after_valid_canonical_bytes(tmp_path, pair):
    plan, run = pair
    record = publish(tmp_path, plan, run)
    changed = ExperimentRun.model_validate(
        run.model_dump()
        | {"subject": run.subject.model_copy(update={"digest": "e" * 64})}
    )
    raw = serialization.run_bytes(changed)
    (tmp_path / "runs" / (record.run_digest + ".json")).unlink()
    (tmp_path / "runs" / (sha256(raw).hexdigest() + ".json")).write_bytes(raw)
    with pytest.raises(StoreError, match="store_corrupt"):
        list(records(tmp_path))


def test_stored_diff_and_export_are_byte_identical_to_public_comparison(tmp_path, pair):
    a = publish(tmp_path, *pair)
    plan, run = pair
    changed = ExperimentRun.model_validate(
        run.model_dump()
        | {
            "metrics": (
                Metric(name="score", value=0.75, origin=EvidenceOrigin.RUNTIME),
            )
        }
    )
    b = publish(tmp_path, plan, changed)
    for left, right in ((a, b), (b, a), (a, a)):
        assert diff_bytes(
            compare_stored_runs(tmp_path, left.run_digest[:12], right.run_digest)
        ) == diff_bytes(compare_runs(left, right))
