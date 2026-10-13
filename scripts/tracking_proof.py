"""Qualify context-local tracking and mixed v1/v2 history from an installed wheel."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import apizr.tracking as tracking
from apizr.experiments.comparison import compare_runs
from apizr.experiments.history import history_bytes, list_runs, show_run
from apizr.experiments.store import DEFAULT_STORE, RunRecordV2


def prove() -> dict[str, object]:
    with TemporaryDirectory(prefix="apizr-tracking-proof-") as directory:
        root = Path(directory).resolve()
        (root / "data.csv").write_bytes(b"value\n1\n")
        (root / "model.bin").write_bytes(b"MODEL")
        with tracking.session(root=root) as capture:
            tracking.log_parameter("rate", 0.1)
            tracking.log_input("data", "data.csv")
            tracking.log_metric("score", 0.75)
            tracking.log_artifact("model", "model.bin")
        assert capture.record is not None
        first = show_run(root / DEFAULT_STORE, capture.record.run_digest)
        assert isinstance(first, RunRecordV2)
        assert first == capture.record
        assert RunRecordV2.model_validate_json(history_bytes(first)) == first
        returned = object()

        @tracking.experiment(parameters=["rate"], root=root)
        def fit(rate: float, secret: str = "not-recorded") -> object:
            tracking.log_metric("score", 0.8)
            return returned

        assert fit(0.2) is returned
        listing = list_runs(root / DEFAULT_STORE)
        assert listing.total == 2
        second = show_run(root / DEFAULT_STORE, listing.runs[0].run_digest)
        assert isinstance(second, RunRecordV2)
        assert second.run.capture.mode.value == "decorated_call"
        assert second.run.call_parameters[0].value == 0.2
        assert "not-recorded" not in second.model_dump_json()
        difference = compare_runs(first, second)
        assert difference.metrics[0].delta == 0.8 - 0.75
        business = RuntimeError("business-secret")
        failed = tracking.session(root=root)
        try:
            with failed:
                raise business
        except RuntimeError as observed:
            assert observed is business
        assert failed.record is not None and failed.record.run.status == "failed"
        assert "business-secret" not in failed.record.model_dump_json()
        assert list_runs(root / DEFAULT_STORE).total == 3
        return {
            "status": "passed",
            "session": first.run_digest,
            "decorated_call": second.run_digest,
            "failure": failed.record.run_digest,
            "history_and_export": "passed",
            "return_and_exception_identity": "passed",
            "unknown_source_not_fabricated": first.run.subject.identity is None,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    assert not Path.cwd().resolve().is_relative_to(checkout)
    assert not Path(tracking.__file__).resolve().is_relative_to(checkout)
    assert all(not Path(item).resolve().is_relative_to(checkout) for item in sys.path)
    assert all(
        importlib.util.find_spec(name) is None
        for name in (
            "fastapi",
            "mcp",
            "nbconvert",
            "numpy",
            "pandas",
            "sklearn",
            "torch",
        )
    )
    args.output.write_text(json.dumps(prove(), indent=2) + "\n")
    print("PASS installed tracking sessions, decorator and canonical history")


if __name__ == "__main__":
    main()
