"""Public import compatibility and one-way CLI/plugin architecture boundaries."""

import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    "local_plugins": "plugins.local",
    "plugin_catalog": "plugins.catalog",
    "plugin_lock": "plugins.lock",
    "plugin_sync": "plugins.sync",
    "plugin_update": "plugins.update",
}
COMMANDS = (
    "ci",
    "clients",
    "delivery",
    "execute",
    "exposure",
    "generate",
    "git_source",
    "graph",
    "mcp",
    "onboarding",
    "plugins",
    "readiness",
    "repository",
    "repository_readiness",
    "scan",
)
ALIASES = {
    **{name + "_cli": "cli.commands." + name for name in COMMANDS},
    "completion": "cli.completion",
    "completion_spec": "cli.completion_spec",
}
for old, new in PACKAGES.items():
    for source in (ROOT / "src/apizr" / new.replace(".", "/")).glob("*.py"):
        if source.name != "__init__.py":
            ALIASES[old + "." + source.stem] = new + "." + source.stem


@pytest.mark.parametrize("old,new", sorted(ALIASES.items()))
def test_old_module_alias_retains_identity_and_patch_visibility(old, new, monkeypatch):
    # Identity preserves class checks, exceptions and monkeypatches, including
    # private helpers used by existing Python integrations.
    before = importlib.import_module("apizr." + old)
    after = importlib.import_module("apizr." + new)
    assert before is after
    marker = object()
    monkeypatch.setattr(before, "_compatibility_probe", marker, raising=False)
    assert after._compatibility_probe is marker


@pytest.mark.parametrize("old,new", sorted(PACKAGES.items()))
def test_old_package_retains_public_objects_and_loaded_submodules(old, new):
    before = importlib.import_module("apizr." + old)
    after = importlib.import_module("apizr." + new)
    for name in dir(after):
        if not name.startswith("_"):
            assert getattr(before, name) is getattr(after, name), name
    with pytest.raises(AttributeError):
        _ = before.nonexistent_public_api


def test_namespace_imports_remain_lazy_and_cli_module_entrypoint_works():
    code = """
import sys
import apizr.cli
import apizr.plugins
assert not any(name.startswith('apizr.plugins.') for name in sys.modules)
assert not any(name.startswith('apizr.cli.commands.') for name in sys.modules)
assert all(name not in sys.modules for name in ('fastapi','mcp','yaml','nbconvert'))
"""
    subprocess.run([sys.executable, "-I", "-c", code], check=True, capture_output=True)
    result = subprocess.run(
        [sys.executable, "-I", "-m", "apizr.cli", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "outerspace-apizr 0.4.4"
    assert not result.stderr


def test_core_and_plugin_management_do_not_depend_on_cli_or_compatibility_facades():
    old_prefixes = tuple("apizr." + name for name in (*PACKAGES, *ALIASES))
    for source in (ROOT / "src/apizr").rglob("*.py"):
        tree = ast.parse(source.read_text())
        if (ast.get_docstring(tree) or "").startswith("Compatibility "):
            continue
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
                if node.module == "apizr":
                    imports.extend("apizr." + alias.name for alias in node.names)
        assert not any(
            name == prefix or name.startswith(prefix + ".")
            for name in imports
            for prefix in old_prefixes
        ), source
        if source.is_relative_to(ROOT / "src/apizr/cli"):
            continue
        assert not any(
            name == "apizr.cli" or name.startswith("apizr.cli.") for name in imports
        ), source
        if source.is_relative_to(ROOT / "src/apizr/plugins"):
            assert not any(
                name.split(".")[0]
                in {"fastapi", "mcp", "apizr_mcp", "apizr_oci", "apizr_attest"}
                for name in imports
            ), source
