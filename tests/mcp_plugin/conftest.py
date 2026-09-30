import sys
from pathlib import Path

import pytest
from analysis_authorization import analysis_policy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/mcp/src"))
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture
def project(tmp_path):
    import shutil

    from apizr_mcp.scope import load_scope

    root = tmp_path / "project"
    shutil.copytree(ROOT / "examples/project-config", root)
    path = root / "apizr.toml"
    return path, load_scope(path, analysis_policy(root))


@pytest.fixture(autouse=True)
def source_distribution_metadata(monkeypatch):
    # Source unit tests do not install the optional distribution. Installed-wheel
    # qualification independently checks real importlib.metadata via initialize.
    import tomllib

    from apizr_mcp import server

    version = tomllib.loads((ROOT / "plugins/mcp/pyproject.toml").read_text())[
        "project"
    ]["version"]

    def installed(name):
        assert name == "outerspace-apizr-mcp"
        return version

    monkeypatch.setattr(server, "version", installed)
