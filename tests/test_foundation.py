"""Regression contracts for generation boundaries and foundation invariants."""

import importlib
import socket
import sys

import nbformat
import pytest

from apizr.extensions.context import Context, ContextException
from apizr.main import convert


def test_unconfigured_context_reports_configuration_error(tmp_path):
    source = tmp_path / "input.py"
    source.write_text("def value():\n    return 1\n")
    context = Context()
    context.input_path = source
    context.output_dir = tmp_path
    context.result = ("code", "content")
    with pytest.raises(ContextException, match="Configuration is not set"):
        context.read_input()
    with pytest.raises(ContextException, match="Configuration is not set"):
        context.write_output("code")


@pytest.mark.parametrize("notebook", [False, True], ids=["script", "notebook"])
def test_generation_is_repeatable_offline_and_execution_requires_import(
    tmp_path, monkeypatch, notebook
):
    marker = tmp_path / "executed"
    source = tmp_path / (
        "trusted_business.ipynb" if notebook else "trusted_business.py"
    )
    code = (
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "def value(x: int = 7):\n    return x\n"
    )
    if notebook:
        nbformat.write(
            nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(code)]), source
        )
    else:
        source.write_text(code)

    def no_network(*args, **kwargs):
        pytest.fail("Generation attempted network access")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    first, second = tmp_path / "first", tmp_path / "second"
    convert(source, first)
    convert(source, second)
    assert not marker.exists()
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {
        p.name: p.read_bytes() for p in second.iterdir()
    }
    monkeypatch.syspath_prepend(str(first))
    try:
        importlib.import_module("trusted_business_api")
        assert marker.exists()
    finally:
        sys.modules.pop("trusted_business_api", None)
        sys.modules.pop("trusted_business", None)


@pytest.mark.parametrize("escape", ["parent", "absolute", "symlink"])
def test_context_output_cannot_escape_directory(tmp_path, escape):
    from apizr.configuration import MainConfiguration

    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    if escape == "symlink":
        (output / "link").symlink_to(outside, target_is_directory=True)
        target = "link/escaped.txt"
    elif escape == "absolute":
        target = outside / "escaped.txt"
    else:
        target = "../outside/escaped.txt"
    context = Context()
    context.config = MainConfiguration()
    context.output_dir = output
    context.result = ("code", "must not escape")
    with pytest.raises(ContextException, match="inside the output directory"):
        context.write_output("code", target)
    assert not (outside / "escaped.txt").exists()
