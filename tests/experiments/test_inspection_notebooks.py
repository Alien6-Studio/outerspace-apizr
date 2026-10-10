"""Cell provenance, unchanged exporter identities and notebook content exclusions."""

import json

import pytest

from apizr.experiments.inspection import inspect_experiment
from apizr.experiments.notebook_source import SourceLocation, code_cells, map_exported
from apizr.experiments.reporting import inspection_bytes, text_report
from apizr.generators.notebooks import inspect_notebook_bytes
from apizr.readiness import assess, report_digest

from .inspection_support import notebook, project


def location(result, pointer):
    matches = [e.location for e in result.locations if e.evidence == pointer]
    assert len(matches) == 1
    return matches[0].cell_index, matches[0].code_cell_index, matches[0].cell_line


def test_realistic_notebook_all_sections_have_original_cell_locations(tmp_path):
    project(tmp_path)
    path = tmp_path / "fraud_detection.ipynb"
    result = inspect_experiment(path)
    assert location(result, "/data/artifacts/0") == (3, 2, 3)
    dynamic = next(
        i
        for i, d in enumerate(result.data.diagnostics)
        if d.code == "dynamic_input_reference"
    )
    assert location(result, f"/data/diagnostics/{dynamic}") == (3, 2, 6)
    assert location(result, "/parameters/signals/0") == (2, 1, 2)
    assert location(result, "/randomness/controls/1") == (4, 3, 1)
    assert location(result, "/metrics/signals/0") == (5, 4, 3)
    assert location(result, "/outputs/signals/0") == (5, 4, 5)
    assert location(result, "/serving/readiness/assessments/0") == (6, 5, 5)
    assert location(result, "/serving/readiness/structured_types/0") == (6, 5, 1)
    assert "cell 3, line 3" in text_report(result)
    old = inspect_notebook_bytes(path.read_bytes(), module_name="fraud_detection")
    assert result.code.source == old.document.source
    assert result.serving.readiness == assess(old.document, old.python_source)
    assert result.code.readiness_digest == report_digest(result.serving.readiness)
    assert b"accuracy: 0.999" not in inspection_bytes(result)


def test_execution_counts_outputs_markdown_are_never_runtime_evidence(tmp_path):
    project(tmp_path)
    path = tmp_path / "fraud_detection.ipynb"
    before = inspect_experiment(path)
    raw = json.loads(path.read_bytes())
    raw["cells"][0]["source"] = "np.random.seed(999)\njoblib.dump(model, 'secret')"
    for cell in raw["cells"][1:]:
        cell["execution_count"] = 987
        cell["outputs"] = [
            {"output_type": "stream", "name": "stdout", "text": "roc_auc=1.0"}
        ]
    path.write_text(json.dumps(raw))
    after = inspect_experiment(path)
    assert before.code.source.digest != after.code.source.digest
    assert before.code.source.transformed_digest != after.code.source.transformed_digest
    assert before.code.signal_digest == after.code.signal_digest
    assert before.locations == after.locations
    for section in (
        "states",
        "data",
        "parameters",
        "randomness",
        "environment",
        "metrics",
        "outputs",
    ):
        assert getattr(before, section) == getattr(after, section)
    assert all(s.parameter.name != "roc_auc" for s in after.parameters.signals)


@pytest.mark.parametrize(
    "rebind, detected",
    [("", True), ("pd = fake\n", False), ("import other as pd\n", False)],
)
def test_cross_cell_imports_and_rebinding(tmp_path, rebind, detected):
    path = tmp_path / "example.ipynb"
    path.write_bytes(
        notebook(
            [
                "import pandas as pd",
                rebind + "\nframe = pd.read_csv(\n  'data.csv'\n)\n",
            ]
        )
    )
    result = inspect_experiment(path)
    assert bool(result.data.artifacts) is detected
    if detected:
        assert location(result, "/data/artifacts/0") == (1, 1, 2)


def test_markers_blank_cells_repeated_definitions_and_unicode(tmp_path):
    path = tmp_path / "example.ipynb"
    path.write_bytes(
        notebook(
            [
                "",
                "\n# In[999]:\ndef predict(x: float):\n return x",
                "# In[1]:\n\nname = 'é'\ndef predict(x: float):\n return x",
            ]
        )
    )
    result = inspect_experiment(path)
    assert result.code.diagnostics
    assert result.serving.readiness.assessments[0].state.value == "ambiguous"
    assert location(result, "/parameters/signals/0") == (2, 2, 3)
    assert location(result, "/serving/readiness/assessments/0") == (1, 1, 3)
    assert all(e.location.cell_index in (1, 2) for e in result.locations)


@pytest.mark.parametrize(
    "raw",
    [
        b"[]",
        b"{}",
        b'{"nbformat":3,"cells":[]}',
        b'{"nbformat":4,"cells":{}}',
        b'{"nbformat":4,"cells":[1]}',
        b'{"nbformat":4,"cells":[{}]}',
        b'{"nbformat":4,"cells":[{"cell_type":"code"}]}',
        b'{"nbformat":4,"cells":[{"cell_type":"code","source":[1]}]}',
        json.dumps({"nbformat": 4, "cells": [{}] * 1025}).encode(),
    ],
)
def test_invalid_cell_structures_refused(raw):
    with pytest.raises(ValueError, match="notebook_cell"):
        code_cells(raw)


@pytest.mark.parametrize(
    "source",
    [
        "%time x",
        "!touch marker",
        "x =",
        "if True:",
        "get_ipython().run_line_magic('time', 'x')",
    ],
)
def test_unsupported_cells_never_executed(tmp_path, source):
    path = tmp_path / "example.ipynb"
    path.write_bytes(notebook([source]))
    with pytest.raises((ValueError, SyntaxError)):
        inspect_experiment(path)
    assert not (tmp_path / "marker").exists()


def test_mapping_refuses_semantic_drift_and_invalid_positions():
    cells = code_cells(notebook(["\r\nx=1\r\n", "pass"]))
    mapped = map_exported(cells, "# header\nx=1\n\npass\n")
    assert mapped.locate_exported("a.ipynb", 2).cell_line == 2
    with pytest.raises(ValueError, match="mapping_disagrees"):
        map_exported(cells, "x=2\npass")
    with pytest.raises(ValueError, match="location_unmapped"):
        mapped.locate("a.ipynb", 100, 0)
    with pytest.raises(ValueError, match="export_location_unmapped"):
        mapped.locate_exported("a.ipynb", 1)
    with pytest.raises(ValueError, match="incomplete_cell_location"):
        SourceLocation(source="a.ipynb", line=1, column=0, cell_index=0)


def test_empty_notebook_is_completed_with_unknown_sections(tmp_path):
    path = tmp_path / "empty.ipynb"
    path.write_bytes(notebook([]))
    result = inspect_experiment(path)
    assert result.states.code.value == "captured"
    assert result.states.data.value == "unknown"
    assert not result.locations
