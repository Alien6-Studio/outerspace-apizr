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
    assert any(name == "fastapi" for name, _ in by_scope["runtime"])
    assert not any(
        name in {"pytest", "mkdocs", "pip-audit"} for name, _ in by_scope["runtime"]
    )
    assert any(name == "pytest" for name, _ in by_scope["development"])
    assert any(name == "mkdocs" for name, _ in by_scope["documentation"])
    assert any(name == "pip-audit" for name, _ in by_scope["security-tooling"])
