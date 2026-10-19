"""Golden exports captured before removing the historical generation pipeline."""

import hashlib
import io
import json
from pathlib import Path

import pytest

from apizr.cli import main
from apizr.notebooks import NotebookTransformr, NotebookTransformrConfiguration

FIXTURES = Path(__file__).parent / "fixtures/notebooks/exporter"
CASES = json.loads((FIXTURES / "baseline.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_historical_exports_and_formatted_scripts_are_byte_identical(case, tmp_path):
    raw = (FIXTURES / (case["name"] + ".ipynb")).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == case["input_sha256"]
    converter = NotebookTransformr(
        NotebookTransformrConfiguration(**case.get("selection", {}))
    )
    if "refusal" in case:
        with pytest.raises(ValueError) as error:
            converter.convert_notebook(io.BytesIO(raw))
        assert str(error.value) == case["refusal"]["message"]
        return
    source, _ = converter.convert_notebook(io.BytesIO(raw))
    assert source.encode() == (FIXTURES / (case["name"] + ".export.py")).read_bytes()
    assert hashlib.sha256(source.encode()).hexdigest() == case["export_sha256"]
    saved = Path(converter.save_script(source, tmp_path, "export.py"))
    assert (
        saved.read_bytes() == (FIXTURES / (case["name"] + ".formatted.py")).read_bytes()
    )
    assert hashlib.sha256(saved.read_bytes()).hexdigest() == case["formatted_sha256"]


@pytest.mark.parametrize("filename", ["../escape.py", "/escape.py", "..\\escape.py"])
def test_explicit_script_export_refuses_directory_components(tmp_path, filename):
    with pytest.raises(ValueError, match="filename without directory"):
        NotebookTransformr().save_script("print(1)", tmp_path, filename)
    assert not list(tmp_path.iterdir())


def test_explicit_script_export_never_overwrites_existing_output(tmp_path):
    converter = NotebookTransformr()
    output = Path(converter.save_script("print(1)", tmp_path, "export.py"))
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        converter.save_script("print(2)", tmp_path, "export.py")
    assert output.read_bytes() == before


@pytest.mark.parametrize(
    "command",
    [[], ["nonesuch"], ["--script", "absent.py"], ["--notebook", "absent.ipynb"]],
)
def test_unknown_and_retired_cli_commands_refuse_without_opening_source(
    command, capsys
):
    assert main(command) == 2
    result = capsys.readouterr()
    assert not result.out
    assert "unknown command" in result.err and "Traceback" not in result.err
    if command and command[0].startswith("--"):
        assert "removed in 0.4.6" in result.err
        assert "apizr inspect" in result.err
