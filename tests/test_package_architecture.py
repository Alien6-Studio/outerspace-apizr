"""Public import compatibility and one-way CLI/plugin architecture boundaries."""

import importlib
import subprocess
import sys
import tomllib
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
INVENTORY = tomllib.loads((ROOT / "architecture/packages.toml").read_text())
ALIASES = {
    path.removesuffix(".py").replace("/", "."): entry["target"].removeprefix("apizr.")
    for path, entry in INVENTORY["compatibility"].items()
    if entry["kind"] == "module"
}


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
    assert result.stdout.strip() == "outerspace-apizr 0.4.4"
    assert not result.stderr


def test_artifact_verification_does_not_import_installed_plugin_lifecycle():
    code = """
import sys
from apizr.plugins.artifacts import requirements, wheel
from apizr.plugins.artifacts.models import Manifest, PluginError
assert not any(name.startswith('apizr.plugins.local') for name in sys.modules)
from apizr.local_plugins.models import Manifest as OldManifest, PluginError as OldError
from apizr.local_plugins import locking as old_requirements, wheel as old_wheel
assert OldManifest is Manifest
assert OldError is PluginError
assert old_requirements is requirements
assert old_wheel is wheel
"""
    subprocess.run([sys.executable, "-I", "-c", code], check=True, capture_output=True)
