"""Run the same compatibility contract on each interpreter in the CI matrix."""

import json
import subprocess
import sys

import pytest

from apizr.compat import DEFAULT_PYTHON, stdlib_module_names
from apizr.configuration import MainConfiguration
from apizr.main import convert


def test_default_target_is_running_interpreter(tmp_path):
    source = tmp_path / "business.py"
    source.write_text("def hello():\n    return 1\n")
    output = tmp_path / "output"
    convert(source, output)
    version = "{}.{}".format(*sys.version_info[:2])
    assert (output / "Dockerfile").read_text().startswith(f"FROM python:{version}-slim")
    assert json.loads((output / "business.json").read_text())["version"] == list(
        sys.version_info[:2]
    )


def test_cli_can_target_python38(tmp_path):
    source = tmp_path / "business.py"
    source.write_text("def hello(name: str = 'world'):\n    return name\n")
    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "apizr.main",
            "--script",
            str(source),
            "--output-dir",
            str(output),
            "--python-version",
            "3.8",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (output / "Dockerfile").read_text().startswith("FROM python:3.8-slim")
    assert json.loads((output / "business.json").read_text())["version"] == [3, 8]
    if DEFAULT_PYTHON > (3, 8):
        # Versions pinned from a newer host could be uninstallable in the 3.8 container.
        assert "fastapi==" not in (output / "requirements.txt").read_text()
        assert "pydantic==" not in (output / "requirements.txt").read_text()


@pytest.mark.parametrize("target", [(3, 7), (3, 15)])
def test_outside_supported_range_is_rejected(target):
    with pytest.raises(ValueError, match="3.8 through 3.14"):
        MainConfiguration(python_version=target).dispatch()


def test_future_target_is_rejected(monkeypatch):
    monkeypatch.setattr("apizr.configuration.DEFAULT_PYTHON", (3, 8))
    with pytest.raises(ValueError, match="at least as recent"):
        MainConfiguration(python_version=(3, 9)).dispatch()


def test_target_syntax_is_checked(tmp_path):
    source = tmp_path / "business.py"
    source.write_text("def hello(value):\n    match value:\n        case 1: return 1\n")
    with pytest.raises(SyntaxError):
        convert(source, tmp_path / "output", python_version="3.8")


def test_stdlib_is_not_inferred_as_third_party(tmp_path):
    assert {
        "ast",
        "json",
        "typing",
        "pathlib",
        "collections",
        "sys",
        "os",
    } <= stdlib_module_names()
    source = tmp_path / "business.py"
    source.write_text(
        "import json\nfrom pathlib import Path\n\ndef hello():\n    return json.loads('1')\n"
    )
    output = tmp_path / "output"
    convert(source, output)
    requirements = (output / "requirements.txt").read_text().splitlines()
    assert not any(line.startswith(("json", "pathlib")) for line in requirements)
