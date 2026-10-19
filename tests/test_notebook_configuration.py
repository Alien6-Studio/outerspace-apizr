"""Explicit code-cell selection and notebook-export configuration admission."""

import io
import json

import nbformat
import pytest
from pydantic import ValidationError

from apizr.notebooks.configuration import (
    NotebookTransformrConfiguration,
)
from apizr.notebooks.exporter import NotebookTransformr


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
