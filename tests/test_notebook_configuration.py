"""Configured multi-cell notebook conversion, resources and invocation."""

import importlib
import io
import json
import shutil
import sys
from pathlib import Path

import nbformat
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apizr.main import convert
from apizr.modules.notebook_transformr.configuration import (
    NotebookTransformrConfiguration,
)
from apizr.modules.notebook_transformr.transformr.nbTransformr import NotebookTransformr


def test_complex_notebook_relocates_and_runs_without_exploration(tmp_path, monkeypatch):
    root = tmp_path / "relocated"
    shutil.copytree(Path(__file__).parents[1] / "examples/complex-notebook", root)
    marker = tmp_path / "executed-during-conversion"
    notebook = root / "pricing.ipynb"
    value = nbformat.read(notebook, as_version=4)
    value.cells[1].source += f"\nPath({str(marker)!r}).touch()\n"
    nbformat.write(value, notebook)
    original = notebook.read_bytes()
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "output"
    result = convert(
        notebook, output, configuration=root / "configuration.yaml", skip_pipreqs=True
    )
    assert not marker.exists()
    assert notebook.read_bytes() == original
    assert (output / "data/prices.json").read_bytes() == (
        root / "data/prices.json"
    ).read_bytes()
    assert "fastapi" in (output / "requirements.txt").read_text()
    assert "get_ipython" not in (output / "pricing.py").read_text()
    monkeypatch.syspath_prepend(str(output))
    try:
        client = TestClient(importlib.import_module(result["api_module"]).app)
        assert marker.exists()  # Explicit server import is the first source execution.
        assert (
            client.post("/quote", json={"product": "coffee", "quantity": 2}).json()
            == 7.0
        )
        assert client.post("/load_prices").status_code == 404
    finally:
        sys.modules.pop("pricing", None)
        sys.modules.pop(result["api_module"], None)


def transform(cells, **selection):
    value = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_code_cell(source, metadata={"tags": tags})
            for tags, source in cells
        ]
    )
    return NotebookTransformr(
        NotebookTransformrConfiguration(**selection)
    ).convert_notebook(io.StringIO(json.dumps(value)))[0]


def test_selection_keeps_order_and_exclusion_wins():
    source = transform(
        [
            (["deploy"], "VALUE = 7"),
            (["deploy", "skip"], "%time 1"),
            (["deploy"], "def read(): return VALUE"),
        ],
        include_tags=["deploy"],
        exclude_tags=["skip"],
    )
    assert source.index("VALUE = 7") < source.index("def read")
    assert "get_ipython" not in source


@pytest.mark.parametrize(
    "selection, message",
    [
        ({"include_tags": ["typo"]}, "tags not found"),
        ({"exclude_tags": ["deploy"]}, "no code cells"),
    ],
)
def test_invalid_selections_refuse(selection, message):
    with pytest.raises(ValueError, match=message):
        transform([(["deploy"], "def f(): pass")], **selection)


@pytest.mark.parametrize("tags", [[""], [" padded"], ["x", "x"], [1], "deploy"])
def test_invalid_configuration_tags(tags):
    with pytest.raises(ValidationError):
        NotebookTransformrConfiguration(include_tags=tags)


def test_selected_magic_still_refuses():
    with pytest.raises(ValueError, match="magics and shell"):
        transform([(["deploy"], "%time 1")], include_tags=["deploy"])


def test_cli_resources_and_requirements_override_configuration(tmp_path):
    source = tmp_path / "sample.py"
    source.write_text("def f(): return 1\n")
    config = tmp_path / "config.yaml"
    config.write_text("requirements: absent.txt\ninclude: [absent-data]\n")
    requirements = tmp_path / "explicit.txt"
    requirements.write_text("requests==2.32.5\n")
    (tmp_path / "data.txt").write_text("payload")
    output = tmp_path / "output"
    convert(
        source,
        output,
        configuration=config,
        requirements=requirements,
        include=["data.txt"],
    )
    assert "requests==2.32.5" in (output / "requirements.txt").read_text()
    assert (output / "data.txt").read_text() == "payload"
