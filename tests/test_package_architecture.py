"""Canonical installed imports, retired-path absence and one-way boundaries."""

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REMOVED = json.loads((ROOT / "tests/fixtures/removed-imports.json").read_text())


@pytest.mark.parametrize("old,target", REMOVED.items(), ids=REMOVED)
def test_canonical_targets_work_and_retired_paths_are_absent(old, target):
    assert importlib.import_module(target).__name__ == target
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(old)


def test_namespace_imports_remain_lazy_and_cli_module_entrypoint_works():
    code = """
import sys
import apizr.cli
import apizr.plugins
import apizr.workspace
assert not any(name.startswith('apizr.plugins.') for name in sys.modules)
assert not any(name.startswith('apizr.cli.commands.') for name in sys.modules)
assert not any(name.startswith('apizr.workspace.') for name in sys.modules)
assert all(name not in sys.modules for name in ('fastapi','mcp','yaml','nbconvert'))
"""
    subprocess.run([sys.executable, "-I", "-c", code], check=True, capture_output=True)
    result = subprocess.run(
        [sys.executable, "-I", "-m", "apizr.cli", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "outerspace-apizr 0.4.6"
    assert not result.stderr


def test_artifact_verification_does_not_import_installed_plugin_lifecycle():
    code = """
import sys
from apizr.plugins.artifacts import requirements, wheel
from apizr.plugins.artifacts.models import Manifest, PluginError
assert not any(name.startswith('apizr.plugins.local') for name in sys.modules)
from apizr.plugins.local.models import Manifest as InstalledManifest, PluginError as InstalledError
assert InstalledManifest is Manifest
assert InstalledError is PluginError

"""
    subprocess.run([sys.executable, "-I", "-c", code], check=True, capture_output=True)


@pytest.mark.parametrize("transport", ["rest", "mcp"])
@pytest.mark.parametrize(
    "scope",
    ["single-local", "single-oci", "single-deny", "repository", "repository-deny"],
)
def test_embedded_closure_resolves_only_canonical_owned_modules(transport, scope):
    import ast

    from apizr.governed.embedding import runtime_files as local
    from apizr.governed_oci.embedding import runtime_files as oci
    from apizr.governed_repository.embedding import runtime_files as repository
    from apizr.subprocess_guard.embedding import strict_files

    files = (
        repository
        if scope.startswith("repository")
        else local
        if scope == "single-local"
        else oci
    )(transport)
    if scope.endswith("deny"):
        files = strict_files(files, repository=scope.startswith("repository"))
    modules = {
        name.removesuffix(".py").removesuffix("/__init__").replace("/", ".")
        for name in files
        if name.startswith("apizr_governed/") and name.endswith(".py")
    }
    assert (
        not {
            "apizr_governed.contract_types",
            "apizr_governed.contract_lowering",
            "apizr_governed.application",
            "apizr_governed.inspection",
        }
        & modules
    )
    for name, data in files.items():
        if not name.startswith("apizr_governed/") or not name.endswith(".py"):
            continue
        package = name.removesuffix(".py").split("/")[:-1]
        for node in ast.walk(ast.parse(data)):
            if isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    base = ".".join(
                        [
                            *package[: len(package) - node.level + 1],
                            *([base] if base else []),
                        ]
                    )
                assert not base.startswith("apizr."), (name, base)
                if base.startswith("apizr_governed"):
                    assert base in modules, (name, base)
            elif isinstance(node, ast.Import):
                for imported in node.names:
                    assert not imported.name.startswith("apizr."), (name, imported.name)
                    if imported.name.startswith("apizr_governed"):
                        assert imported.name in modules, (name, imported.name)
