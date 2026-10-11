"""Installed core-only A/B comparison, deletion proof and fixed-record parity."""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

import apizr.experiments.comparison as implementation
from apizr.experiments.comparison import (
    ChangeState,
    ExperimentDiff,
    compare_runs,
    diff_bytes,
)
from apizr.experiments.comparison_reporting import diff_text
from apizr.experiments.store import RunRecord


def prove(fixtures: Path) -> dict[str, object]:
    fixed = [
        RunRecord.model_validate_json((fixtures / f"{side}.record.json").read_bytes())
        for side in ("a", "b")
    ]
    comparison = compare_runs(*fixed)
    fixed_json, fixed_text = diff_bytes(comparison), diff_text(comparison).encode()
    assert fixed_json == (fixtures / "diff.json").read_bytes()
    assert fixed_text == (fixtures / "diff.txt").read_bytes()
    with tempfile.TemporaryDirectory(prefix="apizr-diff-proof-") as folder:
        root = Path(folder)

        def command(*args: str) -> bytes:
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-m", "apizr.cli", "experiment", *args],
                cwd=root,
                capture_output=True,
                timeout=30,
            )
            assert result.returncode == 0, (result.returncode, result.stderr)
            if args[0] == "run":
                assert b"trusted user code" in result.stderr
            else:
                assert not result.stderr
            return result.stdout

        source, data, output = [
            root / name for name in ("train.py", "data.csv", "model.bin")
        ]
        runs = []
        for depth, score in ((8, 0.941), (12, 0.948)):
            source.write_text(
                f"from pathlib import Path\nmax_depth = {depth}\nscore = {score}\nPath('model.bin').write_bytes(b'model-{depth}')\n"
            )
            data.write_text(f"x\n{depth}\n")
            raw = command(
                "run",
                "train.py",
                "--input",
                "training=data.csv",
                "--metric",
                "roc_auc=score",
                "--output",
                "model=model.bin",
                "--format",
                "json",
            )
            runs.append(json.loads(raw)["run_digest"])
        assert json.loads(command("list", "--format", "json"))["total"] == 2
        assert b"2 shown" in command("list")
        before_json = command("diff", *runs, "--format", "json")
        before_text = command("diff", *runs)
        for path in (source, data, output):
            path.unlink()
        assert command("diff", *runs, "--format", "json") == before_json
        assert command("diff", *runs) == before_text
        moved = root / "moved-history"
        shutil.copytree(root / ".apizr/experiments/v1", moved)
        assert (
            command("diff", *runs, "--store", str(moved), "--format", "json")
            == before_json
        )
        assert command("diff", *runs, "--store", str(moved)) == before_text
        value = ExperimentDiff.model_validate_json(before_json)
        assert value.metrics[0].state == ChangeState.CHANGED
        assert value.metrics[0].delta == 0.948 - 0.941
        assert value.outputs[0].state == ChangeState.CHANGED
        assert value.data[0].content_state == ChangeState.CHANGED
        assert (
            next(p for p in value.parameters if p.name == "max_depth").planned_state
            == ChangeState.CHANGED
        )
        assert value.serving == ChangeState.UNKNOWN
        assert str(root).encode() not in before_json + before_text
        return {
            "status": "passed",
            "run_a": runs[0],
            "run_b": runs[1],
            "real_runs": 2,
            "list_text_json": "passed",
            "diff_text_json": "passed",
            "after_source_data_output_deletion": "passed",
            "store_relocation": "passed",
            "fixed_json_sha256": sha256(fixed_json).hexdigest(),
            "fixed_text_sha256": sha256(fixed_text).hexdigest(),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    assert not Path(implementation.__file__).resolve().is_relative_to(checkout)
    assert all(not Path(entry).resolve().is_relative_to(checkout) for entry in sys.path)
    result = prove(args.fixtures)
    result["installed_outside_checkout"] = True
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
