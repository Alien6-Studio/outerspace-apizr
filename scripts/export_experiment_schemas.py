"""Regenerate the independent Experiment Plan and Experiment Run v1 schemas."""

import json
from pathlib import Path

from apizr.experiments import ExperimentPlan, ExperimentRun
from apizr.experiments.comparison import ExperimentDiff
from apizr.experiments.exposure_model import ExperimentExposureBinding
from apizr.experiments.history import HistoryList, RunSummary
from apizr.experiments.inspection_model import ExperimentInspection
from apizr.experiments.store import RunRecord


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "docs/specs"
    for name, model in (
        ("plan", ExperimentPlan),
        ("run", ExperimentRun),
        ("inspection", ExperimentInspection),
        ("history", HistoryList),
        ("record", RunRecord),
        ("run-result", RunSummary),
        ("diff", ExperimentDiff),
        ("exposure", ExperimentExposureBinding),
    ):
        (root / f"apizr-experiment-{name}-v1.schema.json").write_text(
            json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
