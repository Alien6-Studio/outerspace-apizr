"""Run the same compatibility contract on each interpreter in the CI matrix."""

import json
import subprocess
import sys

import pytest

from apizr.configuration import MainConfiguration
from apizr.main import convert
from apizr.runtime import DEFAULT_PYTHON


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


def test_cli_can_target_python311(tmp_path):
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
            "3.11",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (output / "Dockerfile").read_text().startswith("FROM python:3.11-slim")
    assert json.loads((output / "business.json").read_text())["version"] == [3, 11]
    if DEFAULT_PYTHON > (3, 11):
        # Versions pinned from a newer host could be uninstallable in the 3.11 container.
        assert "fastapi==" not in (output / "requirements.txt").read_text()
        assert "pydantic==" not in (output / "requirements.txt").read_text()


@pytest.mark.parametrize("target", [(3, 8), (3, 9), (3, 10), (3, 15)])
def test_outside_supported_range_is_rejected(target):
    with pytest.raises(ValueError, match="3.11 through 3.14"):
        MainConfiguration(python_version=target).dispatch()


def test_future_target_is_rejected(monkeypatch):
    monkeypatch.setattr("apizr.configuration.DEFAULT_PYTHON", (3, 11))
    with pytest.raises(ValueError, match="at least as recent"):
        MainConfiguration(python_version=(3, 12)).dispatch()


def test_target_syntax_is_checked(tmp_path):
    source = tmp_path / "business.py"
    source.write_text("def hello[T](value: T):\n    return value\n")
    with pytest.raises(SyntaxError):
        convert(source, tmp_path / "output", python_version="3.11")


def test_stdlib_is_not_inferred_as_third_party(tmp_path):
    assert {
        "ast",
        "json",
        "typing",
        "pathlib",
        "collections",
        "sys",
        "os",
    } <= sys.stdlib_module_names
    source = tmp_path / "business.py"
    source.write_text(
        "import json\nfrom pathlib import Path\n\ndef hello():\n    return json.loads('1')\n"
    )
    output = tmp_path / "output"
    convert(source, output)
    requirements = (output / "requirements.txt").read_text().splitlines()
    assert not any(line.startswith(("json", "pathlib")) for line in requirements)


@pytest.mark.parametrize("target", ["3.8", "3.9", "3.10", "3.15"])
def test_cli_rejects_unsupported_target_without_traceback(tmp_path, target):
    source = tmp_path / "business.py"
    source.write_text("def hello():\n    return 1\n")
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
            target,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Supported Python targets are 3.11 through 3.14" in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("target", [(3, 8), (3, 9), (3, 10), (3, 15)])
def test_docker_configuration_rejects_unsupported_target(target):
    from apizr.modules.dockerizr.configuration import DockerizrConfiguration

    with pytest.raises(ValueError, match="3.11 through 3.14"):
        DockerizrConfiguration(python_version=target)


def test_yaml_configuration_rejects_unsupported_target(tmp_path):
    source = tmp_path / "business.py"
    source.write_text("def hello():\n    return 1\n")
    config = tmp_path / "config.yaml"
    config.write_text("python_version: [3, 10]\n")
    with pytest.raises(ValueError, match="3.11 through 3.14"):
        convert(source, tmp_path / "output", configuration=config)


def test_generated_server_requirements_enforce_security_floors(tmp_path):
    from packaging.requirements import Requirement

    source = tmp_path / "business.py"
    source.write_text("def hello():\n    return 1\n")
    output = tmp_path / "output"
    convert(source, output)
    requirements = [
        Requirement(line)
        for line in (output / "requirements.txt").read_text().splitlines()
    ]
    starlette = [req for req in requirements if req.name == "starlette"]
    fastapi = [req for req in requirements if req.name == "fastapi"]
    assert any(
        "1.3.0" not in req.specifier and "1.3.1" in req.specifier for req in starlette
    )
    assert any(
        "0.140.0" not in req.specifier and "0.141.0" in req.specifier for req in fastapi
    )
