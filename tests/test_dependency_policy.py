"""The scoped audit must cover the entire universal lock, not just this host."""

import runpy
import tomllib
from pathlib import Path


def test_audit_scopes_cover_every_locked_dependency_variant(tmp_path):
    root = Path(__file__).resolve().parents[1]
    audit = runpy.run_path(str(root / "scripts/audit_dependencies.py"))
    locked = tomllib.loads((root / "uv.lock").read_text())
    expected = {
        (package["name"], package["version"])
        for package in locked["package"]
        if "registry" in package["source"]
    }
    covered = set()
    by_scope = {}
    for scope in audit["SCOPES"]:
        exported = tomllib.loads(
            audit["export_scope"](root, tmp_path / scope, scope).read_text()
        )
        by_scope[scope] = {
            (package["name"], package["version"]) for package in exported["packages"]
        }
        covered.update(by_scope[scope])
    assert covered == expected
    assert {name for name, _ in by_scope["runtime"]} == {
        "pydantic",
        "pydantic-core",
        "annotated-types",
        "typing-extensions",
        "typing-inspection",
    }
    assert any(name == "fastapi" for name, _ in by_scope["runtime-http"])
    assert any(name == "nbconvert" for name, _ in by_scope["runtime-notebook"])
    assert any(name == "questionary" for name, _ in by_scope["runtime-legacy"])
    assert any(name == "mcp" for name, _ in by_scope["runtime-mcp"])
    assert not any(
        name in {"pytest", "mkdocs", "pip-audit"} for name, _ in by_scope["runtime"]
    )
    assert any(name == "pytest" for name, _ in by_scope["development"])
    assert any(name == "mkdocs" for name, _ in by_scope["documentation"])
    assert any(name == "pip-audit" for name, _ in by_scope["security-tooling"])


def test_dependency_source_policy_refuses_unreviewed_origins_and_missing_hashes():
    import copy

    import pytest

    validate = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts/check_dependency_sources.py")
    )["validate_sources"]
    archive = {
        "url": "https://files.pythonhosted.org/packages/example.whl",
        "hash": "sha256:" + "a" * 64,
    }
    package = {
        "name": "example",
        "version": "1.0",
        "source": {"registry": "https://pypi.org/simple"},
        "wheels": [archive],
    }
    validate({"package": [package]}, "outerspace-apizr")
    for change in (
        {"source": {"git": "https://example.com/repo", "rev": "main"}},
        {"source": {"editable": "../local"}},
        {"source": {"registry": "https://example.com/simple"}},
        {"wheels": []},
        {"wheels": [{**archive, "hash": ""}]},
        {
            "wheels": [
                {**archive, "url": "https://files.pythonhosted.org.evil.test/a.whl"}
            ]
        },
    ):
        bad = {**copy.deepcopy(package), **change}
        with pytest.raises(ValueError):
            validate({"package": [bad]}, "outerspace-apizr")


def test_sbom_exports_cover_the_locked_graph(tmp_path):
    import json
    import subprocess

    root = Path(__file__).parents[1]
    lock = tomllib.loads((root / "uv.lock").read_text())
    output = tmp_path / "validation.cdx.json"
    subprocess.run(
        [
            "uv",
            "export",
            "--locked",
            "--offline",
            "--all-groups",
            "--no-emit-project",
            "--format",
            "cyclonedx1.5",
            "--output-file",
            str(output),
        ],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    sbom = json.loads(output.read_text())
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"
    assert {(p["name"], p["version"]) for p in sbom["components"]} == {
        (p["name"], p["version"]) for p in lock["package"] if "registry" in p["source"]
    }
