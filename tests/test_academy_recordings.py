"""The written Academy must stay bound to the produced lessons, not just video count."""

import copy
import importlib.util
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "recordings", ROOT / "scripts/academy_recordings.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def page_for(record):
    source = (ROOT / "docs" / record["page"]).read_text()
    metadata = yaml.safe_load(source.split("---", 2)[1])
    return source, SimpleNamespace(
        meta=metadata, file=SimpleNamespace(src_uri=record["page"])
    )


def test_all_produced_recordings_have_their_original_narration_and_distinct_course():
    catalogue = module.recordings(ROOT)
    for record in catalogue["lessons"]:
        assert record["recording_version"] == (
            "0.4.3" if record["number"] <= 5 else "0.4.6"
        )
        assert all(len(value) == 64 for value in record["sources"].values())
        source, page = page_for(record)
        rendered = module.lesson_markdown(source, page, catalogue)
        assert "<!-- recording-transcript -->" not in rendered
        for scene in record["chapters"]:
            assert scene["title"] in rendered
            assert scene["narration"] in rendered
            for command in scene["commands"]:
                assert all(line in rendered for line in command["text"].splitlines())


@pytest.mark.parametrize("change", ["video", "page", "number", "identity", "missing"])
def test_a_reused_video_or_an_unrelated_course_is_rejected(change):
    catalogue = module.recordings(ROOT)
    record = catalogue["lessons"][3]  # The produced RGB/HSV MCP lesson.
    source, page = page_for(record)
    if change == "video":
        source = source.replace(record["video_id"], catalogue["lessons"][2]["video_id"])
    elif change == "page":
        page.file.src_uri = catalogue["lessons"][2]["page"]
    elif change == "number":
        page.meta["lesson"] = 3
    elif change == "identity":
        page.meta["recording"] = "invented-recording"
    else:
        del page.meta["recording"]
    with pytest.raises(ValueError):
        module.lesson_markdown(source, page, catalogue)


@pytest.mark.parametrize(
    "corruption", ["download", "duplicate", "timeline", "narration"]
)
def test_missing_or_altered_recording_inputs_stop_the_build(tmp_path, corruption):
    original = module.recordings(ROOT)
    catalogue = copy.deepcopy(original)
    (tmp_path / "academy").mkdir()
    for name in catalogue["downloads"]:
        target = tmp_path / "docs" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "docs" / name, target)
    if corruption == "download":
        name = next(iter(catalogue["downloads"]))
        (tmp_path / "docs" / name).write_bytes(b"wrong teaching material")
    elif corruption == "duplicate":
        catalogue["lessons"][3]["video_id"] = catalogue["lessons"][2]["video_id"]
    elif corruption == "timeline":
        catalogue["lessons"][3]["chapters"][1]["seconds"] = 0
    else:
        catalogue["lessons"][3]["chapters"][0]["narration"] = ""
    (tmp_path / "academy/recordings.json").write_text(json.dumps(catalogue))
    with pytest.raises(ValueError):
        module.recordings(tmp_path)


@pytest.mark.parametrize(
    "number,subjects",
    [
        (1, ["boltons", "more-itertools", "humanize", "slugify", "pipx", "Homebrew"]),
        (2, ["Requests", "v2.32.5", "doctor", "scan", "get", "variadic"]),
        (3, ["keon/algorithms", "gcd,lcm", "48", "18", "HTTP 422"]),
        (
            4,
            [
                "TheAlgorithms/Python",
                "rgb_to_hsv",
                "hsv_to_rgb",
                "structured_content",
                "is_error",
            ],
        ),
        (
            5,
            [
                "pricing.total",
                "Ollama",
                "136.5",
                "prepare_build.py",
                "published: false",
            ],
        ),
        (6, ["fraud_detection.ipynb", "presentation", "signal-check", "not_executed"]),
        (7, ["fraud_detection.ipynb", "model.joblib", "damaged-store", "exit 2"]),
        (8, ["self-comparison", "reverse", "0.68504", "0.65485", "unknown"]),
        (
            9,
            [
                "python:fraud_detection:predict",
                "run_artifact_changed",
                "scikit-learn",
                "joblib",
            ],
        ),
        (10, ["evaluation.csv", "0.35", "0.65", "thresholds.py failure", "ValueError"]),
        (
            11,
            [
                "fraud-thresholds.ipynb",
                "calibration_offset",
                "103",
                "60",
                "first-variant",
            ],
        ),
        (
            12,
            ["Wine", "Restricted Mode", "unsaved comment", "generalization", "0.9630"],
        ),
    ],
)
def test_the_course_keeps_the_recorded_case_and_failure_variant(number, subjects):
    record = module.recordings(ROOT)["lessons"][number - 1]
    source, _ = page_for(record)
    for subject in subjects:
        assert subject in source, (record["id"], subject)
