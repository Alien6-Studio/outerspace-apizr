"""The optional source package is visible only inside its own tests."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins/oci/src"))

from local_plugins.conftest import wheel_factory  # noqa: F401
from repository_interfaces.conftest import evidence

from apizr.repository_interfaces.generator import render_repository_bundle


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    for name, data in render_repository_bundle(*evidence(), interface="rest").items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root
