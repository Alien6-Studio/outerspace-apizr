"""Benchmark evidence fails on unexpected errors and keeps production ceilings."""

import json

import pytest

from apizr.experiments.history import list_runs
from apizr.experiments.store import StoreError
from scripts.qualification.experiments import benchmark_engine as benchmark


def test_measure_retains_samples_and_reports_expected_resource_refusal():
    result = benchmark.measure(lambda: None, 3)
    assert result["outcome"] == "success" and len(result["seconds"]) == 3
    assert (
        result["minimum_seconds"]
        <= result["median_seconds"]
        <= result["maximum_seconds"]
    )

    def refused():
        raise StoreError("store_limit")

    assert benchmark.measure(refused, 2)["outcome"] == "store_limit"


def test_unexpected_or_inconsistent_outcomes_cannot_be_presented_as_timings():
    def corrupt():
        raise StoreError("store_corrupt")

    with pytest.raises(StoreError, match="store_corrupt"):
        benchmark.measure(corrupt, 3)
    attempts = iter([False, True])

    def inconsistent():
        if next(attempts):
            raise StoreError("store_limit")

    with pytest.raises(ValueError, match="benchmark_outcome_unstable"):
        benchmark.measure(inconsistent, 2)


def test_synthetic_fixtures_are_accepted_by_real_engine_and_operations(tmp_path):
    first, last = benchmark.make_history(tmp_path / "store", 10)
    assert first != last
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    for name in ("list", "show", "diff"):
        data = json.loads(
            benchmark.history_operation(tmp_path / "store", first, last, name)()
        )
        assert data["schema_version"].startswith("apizr.experiment-")
    assert list_runs(tmp_path / "store").total == 10
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*.json")}


def test_fixture_setup_never_raises_production_history_limits(tmp_path, monkeypatch):
    from apizr.experiments import store

    first, last = benchmark.make_history(tmp_path / "store", 10)
    monkeypatch.setattr(store, "MAX_ENTRIES", 9)
    for name in ("list", "show", "diff"):
        result = benchmark.measure(
            benchmark.history_operation(tmp_path / "store", first, last, name), 1
        )
        assert result["outcome"] == "store_limit"


def test_profiler_retains_machine_readable_calls_and_human_readable_report(tmp_path):
    first, last = benchmark.make_history(tmp_path / "store", 10)
    calls = benchmark.profile(
        benchmark.history_operation(tmp_path / "store", first, last, "show"),
        tmp_path / "show.prof",
    )
    assert calls["serialization.py:read_run"] == 10
    assert (tmp_path / "show.prof").stat().st_size > 0
    assert "function calls" in (tmp_path / "show.txt").read_text()
