"""Catch stale README expectations before the release installation matrix."""

import json
import subprocess
import sys
from pathlib import Path


def test_current_readme_and_experiment_guides_execute(tmp_path):
    root = Path(__file__).resolve().parents[1]
    report = tmp_path / "experiment-docs.json"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/smoke_experiment_docs.py"),
            str(Path(sys.executable).with_name("apizr")),
            "--output",
            str(report),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    results = json.loads(report.read_text())
    assert results["README.md"]["blocks"] == 1
    assert all(result["status"] == "passed" for result in results.values())
