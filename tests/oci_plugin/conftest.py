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


@pytest.fixture(autouse=True)
def installed_oci_metadata(monkeypatch):
    # Source-only unit tests have no installed OCI distribution. Installed-wheel
    # qualification independently uses real metadata with no patch.
    import tomllib

    import apizr.delivery

    actual = apizr.delivery.version
    declared = tomllib.loads(
        (Path(__file__).parents[2] / "plugins/oci/pyproject.toml").read_text()
    )["project"]["version"]
    monkeypatch.setattr(
        apizr.delivery,
        "version",
        lambda name: declared if name == "outerspace-apizr-oci" else actual(name),
    )
