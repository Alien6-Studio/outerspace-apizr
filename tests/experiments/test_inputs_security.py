"""Source parsing has no execution authority; file reads have one explicit target."""

import builtins
import os
import socket
import subprocess
from pathlib import Path

import pytest

from apizr.experiments import InputDeclaration, discover_inputs, fingerprint_input


def test_hostile_source_never_executes_or_reads_data(monkeypatch, tmp_path):
    marker = tmp_path / "executed"
    source = f"""import pandas as pd
import socket
import subprocess
raise RuntimeError("hostile")
open({str(marker)!r}, "w").write("executed")
socket.create_connection(("example.org",443))
subprocess.run(["false"])
pd.read_csv("secret.csv")
"""

    def forbidden(*args, **kwargs):
        pytest.fail("Static discovery executed source or performed I/O")

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert name.split(".")[0] not in {"pandas", "numpy", "joblib", "pyarrow"}
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", guarded_import)
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(os, "open", forbidden)
        patch.setattr(socket, "create_connection", forbidden)
        patch.setattr(subprocess, "run", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        result = discover_inputs(source, source_reference="train.py")
    assert result.artifacts[0].reference == "secret.csv"
    assert not marker.exists()


def test_only_selected_file_is_read_no_copy_or_leak(tmp_path, monkeypatch, capsys):
    (tmp_path / "selected.csv").write_bytes(b"unique-dataset-secret-marker")
    (tmp_path / "neighbor.csv").write_bytes(b"other")
    original_open = os.open
    file_opens = []

    def checked_open(path, flags, *args, **kwargs):
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)
        if not flags & os.O_DIRECTORY:
            file_opens.append(path)
            assert path == "selected.csv"
            assert flags & os.O_NOFOLLOW and flags & os.O_NONBLOCK
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", checked_open)
    result = fingerprint_input(
        tmp_path, InputDeclaration(name="train", reference="selected.csv")
    )
    assert not result.diagnostics
    assert file_opens == ["selected.csv"]
    assert "unique-dataset-secret-marker" not in result.model_dump_json()
    assert "unique-dataset-secret-marker" not in str(capsys.readouterr())
    assert sorted(item.name for item in tmp_path.iterdir()) == [
        "neighbor.csv",
        "selected.csv",
    ]


def test_symlink_swap_after_admission_is_never_read(tmp_path, monkeypatch):
    selected = tmp_path / "selected.csv"
    selected.write_bytes(b"admitted")
    target = tmp_path / "private.csv"
    target.write_bytes(b"never-read-secret")
    original_open, original_read = os.open, os.read
    reads = []

    def swap(path, flags, *args, **kwargs):
        if path == "selected.csv":
            selected.unlink()
            selected.symlink_to("private.csv")
        return original_open(path, flags, *args, **kwargs)

    def record(fd, count):
        reads.append(fd)
        return original_read(fd, count)

    monkeypatch.setattr(os, "open", swap)
    monkeypatch.setattr(os, "read", record)
    result = fingerprint_input(
        tmp_path, InputDeclaration(name="train", reference="selected.csv")
    )
    assert not reads
    assert result.artifacts[0].digest is None
    assert result.diagnostics[0].code == "input_symlink"
