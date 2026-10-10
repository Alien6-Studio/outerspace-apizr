"""Installed-wheel trusted workload and immutable history proof outside checkout."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

import apizr.experiments.runner as implementation
from apizr.experiments.history import HistoryList, RunSummary
from apizr.experiments.serialization import plan_bytes, run_bytes, validate_run_binding
from apizr.experiments.store import RunRecord


def prove(*, notebook: bool) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="apizr-run-proof-") as folder:
        root = Path(folder)
        source = root / ("train.ipynb" if notebook else "train.py")
        body = """import os
from pathlib import Path
learning_rate = 0.1
learning_rate *= 2
score = {"mean": sum([2, 4, 6]) / 3, "details": [True, None]}
worker_pid = os.getpid()
print("suppressed_workload_secret")
os.write(1, b"suppressed_raw_secret")
Path("model.bin").write_bytes(b"MODEL")
"""
        if notebook:
            source.write_text(
                json.dumps(
                    {
                        "nbformat": 4,
                        "nbformat_minor": 5,
                        "metadata": {},
                        "cells": [
                            {
                                "cell_type": "code",
                                "id": "run-proof",
                                "metadata": {},
                                "source": body,
                                "execution_count": 99,
                                "outputs": [
                                    {
                                        "output_type": "stream",
                                        "name": "stdout",
                                        "text": "stored_output_secret",
                                    }
                                ],
                            },
                        ],
                    }
                )
            )
        else:
            source.write_text(body)
        (root / "data.csv").write_bytes(b"x\n1\n")

        def command(*args: str, expected: int = 0) -> bytes:
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-m", "apizr.cli", "experiment", *args],
                cwd=root,
                capture_output=True,
                timeout=30,
            )
            assert result.returncode == expected, (result.returncode, result.stderr)
            assert b"_secret" not in result.stdout + result.stderr
            if args[0] == "run":
                assert b"trusted user code" in result.stderr
            else:
                assert not result.stderr
            return result.stdout

        inspection = json.loads(command("inspect", source.name, "--format", "json"))
        assert inspection["execution"] == "not_executed"
        assert not (root / ".apizr").exists() and not (root / "model.bin").exists()
        raw = command(
            "run",
            source.name,
            "--input",
            "training=data.csv",
            "--metric",
            "score=score",
            "--metric",
            "worker_pid=worker_pid",
            "--output",
            "model=model.bin",
            "--format",
            "json",
        )
        brief = RunSummary.model_validate_json(raw)
        record = RunRecord.model_validate_json(
            command("show", brief.run_digest, "--format", "json")
        )
        validate_run_binding(record.run, record.plan)
        assert (
            record.run.status == "success" and record.plan.subject.capability_id is None
        )
        assert record.plan.subject.digest == sha256(source.read_bytes()).hexdigest()
        assert record.plan.subject.executable_digest is not None
        assert {m.name: m.value for m in record.run.metrics}["score"] == {
            "mean": 4.0,
            "details": (True, None),
        }
        assert {m.name: m.value for m in record.run.metrics}[
            "worker_pid"
        ] != os.getpid()
        assert {p.name: p.value for p in record.run.effective_parameters}[
            "learning_rate"
        ] == 0.2
        assert record.run.outputs[0].digest == sha256(b"MODEL").hexdigest()
        assert record.run.observed_inputs[0].digest == sha256(b"x\n1\n").hexdigest()
        assert record.run.environment is not None
        assert all(
            p.name == "outerspace-apizr" for p in record.run.environment.packages
        )
        assert not record.run.randomness
        store = root / ".apizr/experiments/v1"
        assert (
            store / "plans" / f"{record.plan_digest}.json"
        ).read_bytes() == plan_bytes(record.plan)
        assert (store / "runs" / f"{record.run_digest}.json").read_bytes() == run_bytes(
            record.run
        )
        listing = HistoryList.model_validate_json(command("list", "--format", "json"))
        assert listing.total == 1 and listing.runs[0] == brief
        assert b"SUCCESS" in command("show", brief.run_digest[:12])
        failure = root / "failure.py"
        failure.write_text('raise RuntimeError("exception_secret")')
        failed = RunSummary.model_validate_json(
            command("run", failure.name, "--format", "json", expected=1)
        )
        assert failed.status == "failed"
        assert b"execution_exception" in command("show", failed.run_digest)
        return {
            "status": "passed",
            "kind": "notebook" if notebook else "python",
            "plan_digest": record.plan_digest,
            "run_digest": record.run_digest,
            "failed_run_digest": failed.run_digest,
            "actual_environment": record.run.environment.model_dump(mode="json"),
            "timing": record.run.timing.model_dump(mode="json")
            if record.run.timing
            else None,
            "exact_canonical_bytes": True,
            "source_bound": True,
            "outputs_fingerprinted": True,
            "fresh_worker": True,
            "workload_logs_suppressed": True,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--notebook", action="store_true")
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    assert not Path(implementation.__file__).resolve().is_relative_to(checkout)
    assert all(not Path(p).resolve().is_relative_to(checkout) for p in sys.path if p)
    args.output.write_text(json.dumps(prove(notebook=args.notebook), indent=2) + "\n")


if __name__ == "__main__":
    main()
