"""Make shared qualification fixtures importable with pytest's console entrypoint."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture
def historical_generator_identity(monkeypatch):
    """Keep frozen 0.4.2 artifact fixtures independent of the installed version."""
    from apizr.delivery import DistributionIdentity
    from apizr.repository_interfaces import generator

    def identity(name):
        assert name == "outerspace-apizr"
        return DistributionIdentity(name=name, version="0.4.2")

    monkeypatch.setattr(generator, "installed_identity", identity)
