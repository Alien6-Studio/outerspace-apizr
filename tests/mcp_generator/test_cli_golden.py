import hashlib
import json
import subprocess
import sys
from pathlib import Path

import nbformat
import pytest

from apizr.cli import main
from apizr.generators.mcp import render
from apizr.inspection import inspect_source

FIXTURE = Path(__file__).parents[1] / "fixtures/mcp/v1"
SOURCE = Path(__file__).parents[1] / "fixtures/rest/v1/pricing.py"


def test_reviewed_mcp_golden_and_all_artifact_hashes():
    source = SOURCE.read_bytes()
    artifacts = render(inspect_source(source, module_name="golden.pricing"), source)
    for name in ("mcp-tools.json", "apizr-mcp.json"):
        assert artifacts[name] == (FIXTURE / name).read_bytes()
    expected = json.loads(artifacts["apizr-mcp.json"])
    assert set(artifacts) == set(expected["artifacts"]) | {"apizr-mcp.json"}
    for name, digest in expected["artifacts"].items():
        assert hashlib.sha256(artifacts[name]).hexdigest() == digest["value"]


@pytest.mark.parametrize("notebook", [False, True])
def test_cli_notebook_and_python(tmp_path, capsys, notebook):
    source = tmp_path / ("sample.ipynb" if notebook else "sample.py")
    code = "def f(x: int): return x\ndef stream(): yield 1"
    if notebook:
        nbformat.write(
            nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(code)]), source
        )
    else:
        source.write_text(code)
    root = tmp_path / "bundle"
    assert (
        main(
            [
                "generate",
                "mcp",
                str(source),
                "--output-dir",
                str(root),
                "--module-name",
                "project.sample",
                "--select",
                "f",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["schema_version"] == "apizr.mcp/v1"
    manifest = json.loads((root / "apizr-mcp.json").read_bytes())
    assert manifest["tools"][0]["capability_id"] == "python:project.sample:f"
    if notebook:
        assert (root / "notebook.ipynb").read_bytes() == source.read_bytes()
        assert (
            hashlib.sha256(
                (root / manifest["executable_path"]).read_bytes()
            ).hexdigest()
            == manifest["source"]["transformed_digest"]["value"]
        )


def test_cli_errors_are_nondestructive(tmp_path, capsys):
    source = tmp_path / "sample.py"
    source.write_text("def stream(): yield 1")
    output = tmp_path / "output"
    assert main(["generate", "mcp", str(source), "--output-dir", str(output)]) == 1
    assert "Generation refused" in capsys.readouterr().err
    assert (
        main(
            [
                "generate",
                "mcp",
                str(source),
                "--output-dir",
                str(output),
                "--select",
                "missing",
            ]
        )
        == 2
    )
    assert not output.exists()
    for flag in ["--force", "--unsafe", "--ignore-readiness"]:
        with pytest.raises(SystemExit) as error:
            main(["generate", "mcp", str(source), "--output-dir", str(output), flag])
        assert error.value.code == 2


def test_compiler_imports_and_rendering_do_not_load_frameworks(tmp_path):
    probe = """import sys
from apizr.inspection import inspect_source
from apizr.generators.mcp import render
from apizr.interfaces import runtime
source = b'def f(x: int): return x'
render(inspect_source(source,module_name='isolation'),source)
assert not any(name.split('.')[0] in {'mcp','mcp_types','fastapi','starlette'} for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
