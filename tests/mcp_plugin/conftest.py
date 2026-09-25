import sys
from pathlib import Path

import pytest

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
    return path, load_scope(path)
