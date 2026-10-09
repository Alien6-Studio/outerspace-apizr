"""Architecture acceptance: misplaced responsibilities must fail qualification."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_package_architecture import check  # noqa: E402


def test_repository_satisfies_declared_composition():
    assert check(ROOT / "src/apizr", ROOT / "architecture/packages.toml") == []
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_package_architecture.py")],
        check=True,
        capture_output=True,
    )


@pytest.mark.parametrize(
    "path,addition,expected",
    [
        ("another_service.py", "def run(): pass\n", "composition namespace"),
        (
            "new_domain/__init__.py",
            '"""Unowned domain."""\n',
            "no declared responsibility",
        ),
        (
            "workspace/extra/__init__.py",
            '"""Unowned child."""\n',
            "no declared responsibility",
        ),
        ("plugins/service.py", "def run(): pass\n", "composition namespace"),
        ("plugins/__init__.py", "class BusinessModel: pass\n", "initializer defines"),
        (
            "project.py",
            "def hidden_business_logic(): pass\n",
            "facade contains implementation",
        ),
        (
            "workspace/project.py",
            "from apizr import plugins_cli\n",
            "imports compatibility path",
        ),
        ("workspace/user.py", "from ..cli import main\n", "domain depends on CLI"),
        (
            "workspace/user.py",
            'import importlib\nimportlib.import_module("apizr.cli")\n',
            "domain depends on CLI",
        ),
        (
            "workspace/files.py",
            "from apizr.repository import ScanPolicy\n",
            "file access depends",
        ),
        (
            "plugins/local/models.py",
            "from ..update import update_plugin\n",
            "local -> update",
        ),
        ("workspace/user.py", "import mcp\n", "optional adapter"),
        (
            "plugins/artifacts/wheel.py",
            "from apizr.plugins.local.activation import enable_extension\n",
            "artifacts -> local",
        ),
        (
            "plugins/lock/operations.py",
            "from apizr.cli.commands.plugins import main\n",
            "domain depends on CLI",
        ),
        (
            "plugins/artifacts/models.py",
            "import apizr_mcp\n",
            "optional adapter",
        ),
    ],
)
def test_architecture_rejects_misplaced_code(tmp_path, path, addition, expected):
    source = tmp_path / "apizr"
    shutil.copytree(
        ROOT / "src/apizr", source, ignore=shutil.ignore_patterns("__pycache__")
    )
    target = source / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text((target.read_text() if target.exists() else "") + "\n" + addition)
    errors = check(source, ROOT / "architecture/packages.toml")
    assert any(path in error and expected in error for error in errors), errors


def test_a_compatibility_docstring_cannot_bypass_dependencies(tmp_path):
    source = tmp_path / "apizr"
    shutil.copytree(
        ROOT / "src/apizr", source, ignore=shutil.ignore_patterns("__pycache__")
    )
    (source / "workspace/user.py").write_text(
        '"""Compatibility harmless-looking description."""\nfrom apizr.cli import main\n'
    )
    assert any(
        "domain depends on CLI" in error
        for error in check(source, ROOT / "architecture/packages.toml")
    )


def test_allowed_plugin_dependencies_cannot_introduce_a_cycle(tmp_path):
    manifest = tmp_path / "packages.toml"
    manifest.write_text(
        (ROOT / "architecture/packages.toml")
        .read_text()
        .replace('local = ["artifacts"]', 'local = ["artifacts", "update"]')
    )
    assert any(
        "contains a cycle" in error for error in check(ROOT / "src/apizr", manifest)
    )
