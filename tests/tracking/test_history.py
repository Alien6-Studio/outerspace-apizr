"""CLI/SDK coexistence, producer-aware pure comparison and validated exports."""

import json
import shutil
from pathlib import Path

import pytest

from apizr import tracking
from apizr.cli import main
from apizr.experiments.comparison import compare_runs, diff_bytes
from apizr.experiments.comparison_reporting import diff_text
from apizr.experiments.history import (
    HistoryListV2,
    HistoryQuery,
    history_bytes,
    list_runs,
    read_history,
    show_run,
    show_text,
)
from apizr.experiments.model import SourceIdentity
from apizr.experiments.runner import run_experiment
from apizr.experiments.store import (
    DEFAULT_STORE,
    RunRecordV2,
    StoreError,
    publish,
    records,
    validate_record,
)

ROOT = Path(__file__).resolve().parents[2]


def test_sdk_and_frozen_cli_history_share_store_and_export(tmp_path, capfd):
    store = tmp_path / DEFAULT_STORE
    shutil.copytree(ROOT / "tests/fixtures/experiments/published-0.4.5", store)
    with tracking.session(root=tmp_path) as capture:
        tracking.log_parameter("rate", 0.2)
        tracking.log_metric("score", 0.9)
    listing = list_runs(store)
    assert listing.total == 3
    sdk = show_run(store, capture.record.run_digest)
    cli = next(r for r in records(store) if not isinstance(r, RunRecordV2))
    difference = compare_runs(cli, sdk)
    assert difference.schema_version == "apizr.experiment-diff/v2"
    assert difference.capture.mode_a.value == "cli_run"
    assert difference.capture.mode_b.value == "sdk_session"
    assert difference.capture.mode_state.value == "changed"
    assert difference.source.state.value == "unknown"
    assert "Capture" in diff_text(difference)
    assert json.loads(diff_bytes(difference))["capture"]["mode_state"] == "changed"
    assert main(["experiment", "list", "--store", str(store)]) == 0
    out, err = capfd.readouterr()
    assert "sdk_session" in out and "rate=0.2" in out and "score=0.9" in out and not err
    assert (
        main(
            [
                "experiment",
                "show",
                sdk.run_digest,
                "--store",
                str(store),
                "--format",
                "json",
            ]
        )
        == 0
    )
    out, err = capfd.readouterr()
    exported = json.loads(out)
    assert exported["schema_version"] == "apizr.experiment-record/v2"
    assert RunRecordV2.model_validate_json(out) == sdk
    assert history_bytes(sdk) == out.encode()
    assert (
        main(
            [
                "experiment",
                "diff",
                cli.run_digest,
                sdk.run_digest,
                "--store",
                str(store),
                "--format",
                "json",
            ]
        )
        == 0
    )
    out, err = capfd.readouterr()
    assert json.loads(out)["capture"]["mode_state"] == "changed" and not err


def test_corrupted_sdk_record_never_bypasses_validation(tmp_path):
    with tracking.session(root=tmp_path) as capture:
        tracking.log_metric("score", 1)
    record = capture.record
    wrong = record.model_copy(update={"run_digest": "b" * 64})
    with pytest.raises(ValueError):
        validate_record(wrong)
    with pytest.raises(ValueError):
        compare_runs(wrong, record)
    path = tmp_path / DEFAULT_STORE / "runs" / (record.run_digest + ".json")
    data = json.loads(path.read_bytes())
    data["plan_digest"] = "a" * 64
    path.write_text(json.dumps(data))
    with pytest.raises(StoreError, match="store_corrupt"):
        list_runs(tmp_path / DEFAULT_STORE)


def test_runner_disables_sdk_to_publish_one_authoritative_record(tmp_path):
    source = tmp_path / "train.py"
    source.write_text(
        'from apizr.tracking import session, log_metric, experiment\n@experiment(parameters=["x"])\ndef fit(x):\n    log_metric("inner", x)\n    return x\nwith session():\n    score = fit(0.75)\n'
    )
    record = run_experiment(source, root=tmp_path)
    assert record.run.status == "success"
    found = list(records(tmp_path / DEFAULT_STORE))
    assert len(found) == 1 and found[0] == record


def test_source_bound_sdk_records_are_comparable_without_fabricated_source(tmp_path):
    (tmp_path / "train.py").write_text("score = 1\n")
    with tracking.session(root=tmp_path, source="train.py") as a:
        pass
    with tracking.session(root=tmp_path, source="train.py") as b:
        pass
    assert isinstance(a.record.run.subject.identity, SourceIdentity)
    difference = compare_runs(a.record, b.record)
    assert difference.source.digest.value == "same"


def test_derived_v2_history_is_versioned_bounded_and_self_consistent(tmp_path):
    for value in (1, 2):
        with tracking.session(root=tmp_path):
            tracking.log_metric("score", value)
    listing = list_runs(tmp_path / DEFAULT_STORE)
    assert read_history(history_bytes(listing)) == listing
    for change, code in [
        ({"total": 0}, "history_counts_invalid"),
        ({"query": HistoryQuery(limit=1)}, "history_counts_invalid"),
        ({"runs": (listing.runs[0], listing.runs[0])}, "history_duplicate_run"),
        ({"runs": tuple(reversed(listing.runs))}, "history_order_invalid"),
    ]:
        with pytest.raises(ValueError, match=code):
            HistoryListV2.model_validate(listing.model_copy(update=change))
    with pytest.raises(ValueError, match="history_artifact_limit"):
        read_history(b" " * (8 * 1024 * 1024 + 4097))


def test_cross_version_store_binding_is_refused_before_publication(tmp_path):
    from apizr.experiments import read_plan

    with tracking.session(root=tmp_path) as capture:
        pass
    v1 = read_plan((ROOT / "tests/fixtures/experiments/v1/plan.json").read_bytes())
    destination = tmp_path / "mixed"
    with pytest.raises(StoreError, match="store_schema_binding_mismatch"):
        publish(destination, v1, capture.record.run)
    assert not destination.exists()


def test_failed_sdk_display_keeps_diagnostics_and_source_unknown(tmp_path):
    with pytest.raises(RuntimeError):
        with tracking.session(root=tmp_path) as capture:
            raise RuntimeError("secret")
    output = show_text(capture.record)
    assert "Source: unknown" in output and "tracking_workload_failed" in output
    assert "secret" not in output


def test_unknown_capture_cannot_bypass_exposure_authority(tmp_path, capfd):
    with tracking.session(root=tmp_path) as capture:
        pass
    destination = tmp_path / "service"
    assert (
        main(
            [
                "experiment",
                "expose",
                capture.record.run_digest,
                "--root",
                str(tmp_path),
                "--capability",
                "python:train:predict",
                "--interface",
                "rest",
                "--output-dir",
                str(destination),
            ]
        )
        == 2
    )
    assert not destination.exists()
