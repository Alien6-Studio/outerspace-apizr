"""Lazy command resolution, exact forwarding and optional dependency boundaries."""

import subprocess
import sys
from types import SimpleNamespace

import pytest

from apizr import cli


@pytest.mark.parametrize("command,target", sorted(cli.COMMAND_TARGETS.items()))
def test_dispatch_imports_only_selected_adapter(command, target, monkeypatch):
    calls = []

    def resolve(module):
        calls.append(module)
        assert module == target[0]
        return SimpleNamespace(**{target[1]: lambda arguments: (arguments, 17)})

    monkeypatch.setattr(cli, "import_module", resolve)
    assert cli.main([command, "--help", "value"]) == (["--help", "value"], 17)
    assert calls == [target[0]]


def test_all_command_targets_resolve_without_optional_sdks():
    code = """
import importlib
import importlib.abc
import sys

class NoOptionalSDK(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'fastapi', 'mcp', 'nbconvert', 'black', 'yaml', 'questionary', 'jinja2'
        }:
            raise AssertionError('optional dependency imported: ' + fullname)

sys.meta_path.insert(0, NoOptionalSDK())
from apizr.cli import COMMAND_TARGETS
assert not any(name.startswith('apizr.cli.commands.') for name in sys.modules)
for module, attribute in COMMAND_TARGETS.values():
    assert callable(getattr(importlib.import_module(module), attribute))
"""
    subprocess.run([sys.executable, "-I", "-c", code], check=True, capture_output=True)
