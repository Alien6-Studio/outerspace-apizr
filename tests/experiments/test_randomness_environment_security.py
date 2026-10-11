"""Producers do not execute hostile source or enumerate secret machine state."""

import builtins
import importlib
import importlib.metadata
import os
import socket
import subprocess
import urllib.request

from apizr.experiments import capture_runtime_environment, discover_randomness


def test_source_and_runtime_no_execution_import_install_or_network(
    monkeypatch, tmp_path
):
    sentinel = tmp_path / "must-not-exist"
    source = f"""import numpy as np
import sklearn.cluster as cluster
import torch
import tensorflow as tf
import subprocess, socket
open({str(sentinel)!r}, 'w').write('executed')
subprocess.run(['pip', 'install', 'numpy'])
socket.create_connection(('example.org',443))
raise RuntimeError('must never execute')
np.random.seed(42)
cluster.KMeans(random_state=42)
torch.manual_seed(42)
tf.random.set_seed(42)
"""
    seen = []

    def version(name):
        seen.append(name)
        return "0.4.4"

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden producer side effect")

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert name.split(".")[0] not in {
            "numpy",
            "pandas",
            "sklearn",
            "torch",
            "tensorflow",
            "joblib",
            "pip",
            "uv",
        }
        return original(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(importlib.metadata, "version", version)
        patch.setattr(importlib.metadata, "distributions", forbidden)
        patch.setattr(importlib, "import_module", forbidden)
        patch.setattr(builtins, "__import__", guarded)
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(builtins, "exec", forbidden)
        patch.setattr(builtins, "eval", forbidden)
        patch.setattr(os, "system", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        patch.setattr(subprocess, "run", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        patch.setattr(urllib.request, "urlopen", forbidden)
        found = discover_randomness(source, source_reference="train.py")
        observed = capture_runtime_environment(
            distributions=found.relevant_distributions
        )
    assert len(found.controls) == 6
    assert seen == ["numpy", "outerspace-apizr", "scikit-learn", "tensorflow", "torch"]
    assert len(observed.evidence.packages) == 5
    assert not sentinel.exists()


def test_environment_variables_are_not_read_or_hashed(monkeypatch):
    class ForbiddenEnvironment:
        def __getitem__(self, key):
            raise AssertionError("environment variable read")

        def __iter__(self):
            raise AssertionError("environment variable enumeration")

        def get(self, *args):
            raise AssertionError("environment variable read")

        def items(self):
            raise AssertionError("environment variable enumeration")

    # Metadata itself can use interpreter import paths; select its trusted factual
    # response here so this test specifically forbids producer environment reads.
    with monkeypatch.context() as patch:
        patch.setattr(importlib.metadata, "version", lambda name: "0.4.4")
        patch.setattr(os, "environ", ForbiddenEnvironment())
        capture_runtime_environment()
