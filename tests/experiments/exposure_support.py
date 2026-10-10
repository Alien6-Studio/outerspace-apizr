"""Small core-only Run/resource project shared by bridge qualification."""

import json
from hashlib import sha256

from apizr.experiments.inspection import inspect_experiment
from apizr.experiments.model import (
    EnvironmentEvidence,
    EvidenceOrigin,
    ExperimentRun,
    OutputArtifact,
    PackageEvidence,
)
from apizr.experiments.planning import derive_plan
from apizr.experiments.serialization import plan_digest, run_digest
from apizr.experiments.store import RunRecord
from apizr.workspace.operator_policy import OperatorPolicy

SOURCE = """from pathlib import Path
from typing import TypedDict
from helper import _predict

class PredictionInput(TypedDict):
    value: int

def predict(request: PredictionInput) -> dict[str, list[tuple[int, bool]]]:
    return {"predictions": [(_predict(request["value"]), True)]}

def train() -> str:
    return "private training helper"
"""
HELPER = """import json
from pathlib import Path

def _predict(value: int) -> int:
    model = json.loads(Path(__file__).with_name("model.json").read_text())
    return value * model["multiplier"]
"""


def authority(root):
    return OperatorPolicy.model_validate(
        {
            "schema": "apizr.operator-policy/v1",
            "grants": (
                {
                    "adapter": "repository",
                    "operation": "analyze",
                    "target": {"kind": "local", "root": str(root)},
                    "permissions": ("source.analyze",),
                },
            ),
        }
    )


def project(root, *, notebook=False, source=SOURCE):
    root.mkdir(parents=True, exist_ok=True)
    path = root / ("serving.ipynb" if notebook else "serving.py")
    if notebook:
        path.write_text(
            json.dumps(
                {
                    "nbformat": 4,
                    "nbformat_minor": 5,
                    "metadata": {},
                    "cells": [
                        {
                            "cell_type": "code",
                            "id": "serving",
                            "metadata": {},
                            "execution_count": None,
                            "outputs": [],
                            "source": source,
                        }
                    ],
                }
            )
        )
    else:
        path.write_text(source)
    (root / "helper.py").write_text(HELPER)
    (root / "unrelated.py").write_text("def duplicate(): pass\ndef duplicate(): pass\n")
    (root / "admin.py").write_text("def admin() -> int: return 1\n")
    (root / "model.json").write_text('{"multiplier": 3}')
    (root / "debug.json").write_text('{"private": true}')
    return path


def record_for(path):
    """Fixed fictional observation for deterministic tests, separate from real Runs."""
    plan = derive_plan(inspect_experiment(path))
    outputs = tuple(
        OutputArtifact(
            name=name,
            reference=name + ".json",
            digest=sha256((path.parent / (name + ".json")).read_bytes()).hexdigest(),
            size=(path.parent / (name + ".json")).stat().st_size,
            origin=EvidenceOrigin.RUNTIME,
        )
        for name in ("model", "debug")
    )
    run = ExperimentRun(
        plan_digest=plan_digest(plan),
        subject=plan.subject,
        status="success",
        outputs=outputs,
        environment=EnvironmentEvidence(
            packages=(
                PackageEvidence(
                    name="example-package",
                    version="1.2.3",
                    origin=EvidenceOrigin.RUNTIME,
                ),
                PackageEvidence(
                    name="unused-package",
                    version="9.8.7",
                    origin=EvidenceOrigin.RUNTIME,
                ),
            )
        ),
    )
    return RunRecord(
        plan=plan, run=run, plan_digest=plan_digest(plan), run_digest=run_digest(run)
    )


def changed_record(record, **changes):
    run = type(record.run).model_validate(record.run.model_copy(update=changes))
    return RunRecord(
        plan=record.plan,
        run=run,
        plan_digest=record.plan_digest,
        run_digest=run_digest(run),
    )
