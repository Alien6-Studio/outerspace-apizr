"""Declared interpreter support must reach real CI, not just package metadata."""

import json
import re
import tomllib
from pathlib import Path

import pytest
import yaml

from apizr.environment.python_target import MAX_PYTHON, MIN_PYTHON, parse_python_target
from scripts.qualification.packaging.coordinated_distributions import (
    PROJECTS,
    QUALIFICATION_TARGETS,
    SUPPORTED_PYTHONS,
    required_targets,
)

ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return yaml.safe_load((ROOT / f".github/workflows/{name}.yml").read_text())["jobs"]


def test_python_support_cannot_drift_between_metadata_runtime_and_ci():
    assert MIN_PYTHON == (3, 11) and MAX_PYTHON == (3, 15)
    assert (
        tuple(f"3.{i}" for i in range(MIN_PYTHON[1], MAX_PYTHON[1] + 1))
        == SUPPORTED_PYTHONS
    )
    for path in PROJECTS.values():
        project = tomllib.loads((path / "pyproject.toml").read_text())["project"]
        assert project["requires-python"] == ">=3.11,<3.16"
    launcher = ROOT / "plugins/mcp/distribution"
    assert (
        tomllib.loads((launcher / "pyproject.toml").read_text())["project"][
            "requires-python"
        ]
        == ">=3.11,<3.16"
    )
    assert (
        json.loads((launcher / "manifest.json").read_text())["compatibility"][
            "runtimes"
        ]["python"]
        == ">=3.11,<3.16"
    )
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    classifiers = {
        value.rsplit(" :: ", 1)[-1]
        for value in project["classifiers"]
        if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", value)
    }
    assert classifiers == set(SUPPORTED_PYTHONS)
    ci = workflow("ci")
    for job in ("compatibility", "container"):
        assert tuple(ci[job]["strategy"]["matrix"]["python"]) == SUPPORTED_PYTHONS
    assert set(ci["macos"]["strategy"]["matrix"]["python"]) == {"3.11", "3.14", "3.15"}
    actual = {
        (t["os"], t["python"])
        for t in ci["release-target"]["strategy"]["matrix"]["include"]
    }
    assert actual == set(QUALIFICATION_TARGETS)
    for name, job in (
        ("mcp-server-plugin", "stdio"),
        ("extension-packaging", "uv-tool"),
    ):
        matrix = workflow(name)[job]["strategy"]["matrix"]
        versions = set(matrix.get("python", [])) | {
            item["python"] for item in matrix.get("include", [])
        }
        assert versions == set(SUPPORTED_PYTHONS)
    action = yaml.safe_load((ROOT / "action.yml").read_text())
    case = next(
        step["run"]
        for step in action["runs"]["steps"]
        if 'case "$APIZR_PYTHON_VERSION"' in step.get("run", "")
    )
    assert set(re.findall(r"3\.\d+", case)) == set(SUPPORTED_PYTHONS)
    # The public Action default stays usable with its still-published core default.
    assert action["inputs"]["python-version"]["default"] == "3.14"
    for version in SUPPORTED_PYTHONS:
        assert parse_python_target(version) == tuple(map(int, version.split(".")))
    for version in ("3.10", "3.16", "4.0"):
        with pytest.raises(ValueError, match="3.11 through 3.15"):
            parse_python_target(version)


def test_declared_candidate_targets_cannot_be_silently_reduced():
    declared = {"qualification_targets": [list(item) for item in QUALIFICATION_TARGETS]}
    assert required_targets(declared) == QUALIFICATION_TARGETS
    declared["qualification_targets"].pop()
    with pytest.raises(ValueError, match="Unreviewed"):
        required_targets(declared)


def test_homebrew_probe_prepares_wheels_for_its_formula_interpreter():
    formula = (
        ROOT / "scripts/qualification/extensions/prepare_extension_homebrew.py"
    ).read_text()
    version = re.search(r'depends_on "python@(3\.\d+)"', formula).group(1)
    steps = workflow("extension-packaging")["homebrew"]["steps"]
    setup = next(step for step in steps if "setup-uv@" in step.get("uses", ""))
    assert setup["with"]["python-version"] == version
    commands = [step.get("run", "") for step in steps]
    # Hosted runner snapshots can predate the newly supported Homebrew formula.
    assert commands.index("brew update") < next(
        i for i, command in enumerate(commands) if command.startswith("brew install ")
    )


def test_http_dependencies_keep_acceleration_without_a_reload_build():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    for name in ("http", "mcp"):
        requirements = project["optional-dependencies"][name]
        assert not any(
            "uvicorn[standard]" in value or "watchfiles" in value
            for value in requirements
        )
        assert all(
            any(value.startswith(package + ">=") for value in requirements)
            for package in ("uvicorn", "uvloop", "httptools", "websockets")
        )
