"""Exercise the installed inspector outside the checkout, with I/O and import guards."""

import argparse
import builtins
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import apizr.experiments.inspection as implementation
from apizr.experiments.inspection import inspect_experiment
from apizr.experiments.inspection_model import ExperimentInspection
from apizr.experiments.reporting import inspection_bytes

FRAMEWORKS = {"pandas", "numpy", "sklearn", "torch", "tensorflow", "joblib"}


def guarded_inspection(path: Path) -> ExperimentInspection:
    """Any forbidden attempt fails this proof, including an attempted output read."""
    imported = builtins.__import__
    open_file, open_fd = builtins.open, os.open
    before = {name for name in sys.modules if name.split(".")[0] in FRAMEWORKS}

    def forbidden(*args, **kwargs):
        raise AssertionError("inspection attempted execution, network or write")

    def import_guard(name, *args, **kwargs):
        assert name.split(".")[0] not in FRAMEWORKS | {path.stem}
        return imported(name, *args, **kwargs)

    def file_guard(file, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in "wax+")
        if isinstance(file, (str, bytes, os.PathLike)):
            name = os.fsdecode(file)
            assert not name.endswith("fraud.joblib")
        return open_file(file, mode, *args, **kwargs)

    def fd_guard(file, flags, *args, **kwargs):
        assert not os.fsdecode(file).endswith("fraud.joblib")
        assert not flags & (
            os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        )
        return open_fd(file, flags, *args, **kwargs)

    with (
        patch.object(builtins, "__import__", import_guard),
        patch.object(builtins, "open", file_guard),
        patch.object(io, "open", file_guard),
        patch.object(os, "open", fd_guard),
        patch.object(os, "system", forbidden),
        patch.object(subprocess, "Popen", forbidden),
        patch.object(socket, "socket", forbidden),
        patch.object(socket, "create_connection", forbidden),
    ):
        result = inspect_experiment(path)
    assert {name for name in sys.modules if name.split(".")[0] in FRAMEWORKS} == before
    return result


def prove(fixtures: Path, *, notebook: bool) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="apizr-inspection-proof-") as directory:
        root = Path(directory)
        shutil.copytree(fixtures, root, dirs_exist_ok=True)
        (root / "artifacts").mkdir()
        (root / "artifacts/fraud.joblib").write_bytes(
            b"stale output must remain unread"
        )
        source = root / ("fraud_detection.ipynb" if notebook else "train.py")
        before = {
            str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob("*")
            if p.is_file()
        }
        started = time.perf_counter()
        result = guarded_inspection(source)
        elapsed = time.perf_counter() - started
        assert (
            result.data.artifacts[0].digest
            == sha256((root / "data/train.csv").read_bytes()).hexdigest()
        )
        assert result.states.randomness.value == "uncontrolled"
        assert result.states.environment.value == "partial"
        assert len(result.metrics.signals) == 2 and len(result.outputs.signals) == 1
        assert result.serving.capabilities[0].id == f"python:{source.stem}:predict"
        if notebook:
            assert all(
                item.location.cell_index is not None for item in result.locations
            )
        else:
            assert not any(name in sys.modules for name in FRAMEWORKS)
        payload = inspection_bytes(result)
        for format_name in ("text", "json"):
            response = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-m",
                    "apizr.cli",
                    "experiment",
                    "inspect",
                    str(source),
                    "--format",
                    format_name,
                ],
                cwd=root,
                check=True,
                capture_output=True,
            )
            assert not response.stderr
            if format_name == "json":
                assert response.stdout == payload
                assert (
                    ExperimentInspection.model_validate_json(response.stdout) == result
                )
            else:
                headings = [
                    line.split(" — ")[0]
                    for line in response.stdout.decode().splitlines()
                    if " — " in line
                ]
                assert headings == [
                    "Code",
                    "Data",
                    "Parameters",
                    "Randomness",
                    "Environment",
                    "Metrics",
                    "Outputs",
                    "Serving",
                ]
        assert before == {
            str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob("*")
            if p.is_file()
        }
        assert str(root).encode() not in payload
        return {
            "status": "passed",
            "kind": "notebook" if notebook else "python",
            "inspection_sha256": sha256(payload).hexdigest(),
            "no_execution": True,
            "forbidden_calls": 0,
            "files_unchanged": True,
            "seconds": elapsed,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--notebook", action="store_true")
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    assert not Path(implementation.__file__).resolve().is_relative_to(checkout)
    assert all(not Path(p).resolve().is_relative_to(checkout) for p in sys.path if p)
    result = prove(args.fixtures, notebook=args.notebook)
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
