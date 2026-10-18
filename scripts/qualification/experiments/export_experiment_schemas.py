"""Regenerate canonical experiment and editor wire schemas."""

import json
from pathlib import Path

from apizr.editor_contracts.model import (
    EditorRequest,
    EditorResponse,
    EngineCapabilities,
)
from apizr.experiments import ExperimentPlan, ExperimentRun
from apizr.experiments.capture_model import ExperimentPlanV2, ExperimentRunV2
from apizr.experiments.comparison import ExperimentDiff, ExperimentDiffV2
from apizr.experiments.exposure_model import (
    ExperimentExposureBinding,
    ExperimentExposureBindingV2,
)
from apizr.experiments.history import (
    HistoryList,
    HistoryListV2,
    RunSummary,
    RunSummaryV2,
)
from apizr.experiments.inspection_model import ExperimentInspection
from apizr.experiments.store import RunRecord, RunRecordV2
from apizr.scientific_providers.contracts.selection import (
    ProviderReport,
    ProviderSelection,
)


def main() -> None:
    root = Path(__file__).resolve().parents[3] / "specs"
    for name, model in (
        ("provider-selection", ProviderSelection),
        ("scientific-providers", ProviderReport),
    ):
        (root / f"apizr-{name}-v1.schema.json").write_text(
            json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    for name, model in (
        ("request", EditorRequest),
        ("response", EditorResponse),
        ("capabilities", EngineCapabilities),
    ):
        (root / f"apizr-editor-{name}-v1.schema.json").write_text(
            json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
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
    for name, model in (
        ("plan", ExperimentPlanV2),
        ("run", ExperimentRunV2),
        ("record", RunRecordV2),
        ("history", HistoryListV2),
        ("run-result", RunSummaryV2),
        ("diff", ExperimentDiffV2),
        ("exposure", ExperimentExposureBindingV2),
    ):
        (root / f"apizr-experiment-{name}-v2.schema.json").write_text(
            json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
