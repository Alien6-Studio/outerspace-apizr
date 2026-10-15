"""Make shared qualification fixtures importable with pytest's console entrypoint."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def pytest_configure(config):
    """Keep the real shared Docker boundary qualification in one process."""
    if os.environ.get("APIZR_TEST_OCI_IMAGE") and (
        config.getoption("numprocesses", default=0)
        or config.getoption("dist", default="no") != "no"
    ):
        raise pytest.UsageError("APIZR_TEST_OCI_IMAGE requires serial pytest (-n 0)")


def pytest_collection_modifyitems(items):
    for item in items:
        if "worker_image" in item.fixturenames:
            item.add_marker(pytest.mark.serial)


@pytest.fixture
def historical_generator_identity(monkeypatch):
    """Keep frozen 0.4.2 artifact fixtures independent of the installed version."""
    from apizr.delivery import DistributionIdentity
    from apizr.repository_interfaces import generator

    def identity(name):
        assert name == "outerspace-apizr"
        return DistributionIdentity(name=name, version="0.4.2")

    monkeypatch.setattr(generator, "installed_identity", identity)
