"""No source execution, model loading, network or environment dump in producers."""

import builtins
import importlib
import os
import pickle
import socket
import subprocess
from pathlib import Path

import pytest

from apizr.experiments import (
    OutputDeclaration,
    capture_metric,
    discover_metrics,
    discover_outputs,
    fingerprint_output,
)


def test_hostile_source_is_only_ast(monkeypatch, tmp_path):
    marker = tmp_path / "executed"
    source = f"""from sklearn.metrics import roc_auc_score
import joblib
import socket
import subprocess
open({str(marker)!r}, "w").write("executed")
socket.create_connection(("example.org",443))
subprocess.run(["false"])
raise RuntimeError("private-source-sentinel")
score=roc_auc_score(hostile(),predictions)
joblib.dump(model,"artifacts/model.joblib")
"""

    def forbidden(*args, **kwargs):
        pytest.fail("static producer performed I/O or execution")

    original = builtins.__import__

    def import_guard(name, *args, **kwargs):
        assert name.split(".")[0] not in {
            "sklearn",
            "numpy",
            "joblib",
            "torch",
            "onnx",
            "safetensors",
        }
        return original(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", import_guard)
        patch.setattr(importlib, "import_module", forbidden)
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(os, "open", forbidden)
        patch.setattr(Path, "exists", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        patch.setattr(subprocess, "run", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        metrics = discover_metrics(source, source_reference="train.py")
        outputs = discover_outputs(source, source_reference="train.py")
    assert len(metrics.signals) == len(outputs.signals) == 1
    assert (
        "private-source-sentinel"
        not in metrics.model_dump_json() + outputs.model_dump_json()
    )
    assert not marker.exists()


def test_output_bytes_are_not_deserialized_or_uploaded(monkeypatch, tmp_path, capsys):
    marker = tmp_path / "executed"
    # A hostile pickle opcode stream, used only as opaque bytes.
    payload = b"cos\nsystem\n(S'touch " + str(marker).encode() + b"'\ntR."
    (tmp_path / "model.joblib").write_bytes(payload)

    def forbidden(*args, **kwargs):
        raise AssertionError("output deserialization, network or process execution")

    original = builtins.__import__

    def import_guard(name, *args, **kwargs):
        assert name.split(".")[0] not in {
            "joblib",
            "torch",
            "onnx",
            "safetensors",
            "numpy",
            "sklearn",
        }
        return original(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", import_guard)
        patch.setattr(importlib, "import_module", forbidden)
        patch.setattr(pickle, "load", forbidden)
        patch.setattr(pickle, "loads", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        patch.setattr(subprocess, "run", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        patch.setattr(os, "system", forbidden)
        result = fingerprint_output(
            tmp_path, OutputDeclaration(name="model", reference="model.joblib")
        )
    assert len(result.artifacts) == 1 and not result.diagnostics
    assert not marker.exists()
    assert str(marker) not in result.model_dump_json() + str(capsys.readouterr())


def test_producers_do_not_inspect_environment_variables(monkeypatch, tmp_path):
    class ForbiddenEnvironment(dict):
        def __iter__(self):
            raise AssertionError("environment enumeration")

        def __getitem__(self, key):
            raise AssertionError("environment access")

        def get(self, *args):
            raise AssertionError("environment access")

    (tmp_path / "model.joblib").write_bytes(b"opaque")
    with monkeypatch.context() as patch:
        patch.setattr(os, "environ", ForbiddenEnvironment())
        assert capture_metric("score", 0.91).value == 0.91
        assert discover_metrics("", source_reference="train.py").signals == ()
        assert discover_outputs("", source_reference="train.py").signals == ()
        assert fingerprint_output(
            tmp_path, OutputDeclaration(name="model", reference="model.joblib")
        ).artifacts
