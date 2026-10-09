"""Exact-byte observations, descriptor safety, and experiment identity."""

import errno
import hashlib
import os
import socket
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.experiments import (
    EvidenceOrigin as O,
)
from apizr.experiments import (
    ExecutionIntent,
    ExperimentPlan,
    FingerprintPolicy,
    InputArtifact,
    InputDeclaration,
    SourceIdentity,
    discover_inputs,
    fingerprint_input,
    fingerprint_inputs,
    inputs,
    parse_input_declaration,
    plan_bytes,
    plan_digest,
)


def declaration(reference="data.csv", name="training"):
    return InputDeclaration(name=name, reference=reference)


def code(result):
    assert result.artifacts[0].digest is result.artifacts[0].size is None
    assert result.artifacts[0].content_origin is O.UNKNOWN
    return result.diagnostics[0].code


def test_exact_bytes_and_declared_vs_observed_origin(tmp_path, monkeypatch):
    data = b"sensitive-row-marker\x00\xff\r\n"
    (tmp_path / "data.csv").write_bytes(data)
    monkeypatch.setattr(inputs, "_CHUNK_BYTES", 3)
    result = fingerprint_input(tmp_path, declaration())
    (artifact,) = result.artifacts
    assert not result.diagnostics
    assert artifact.digest == hashlib.sha256(data).hexdigest()
    assert artifact.size == len(data)
    assert artifact.origin is O.DECLARED and artifact.content_origin is O.STATIC
    assert artifact.format_hint == "csv"
    assert "sensitive-row-marker" not in result.model_dump_json()
    assert str(tmp_path) not in result.model_dump_json()


@pytest.mark.parametrize(
    "suffix,hint",
    [
        ("csv", "csv"),
        ("parquet", "parquet"),
        ("npy", "numpy"),
        ("npz", "numpy"),
        ("joblib", "joblib"),
        ("pkl", None),
        ("CSV", None),
    ],
)
def test_suffix_allowlist_and_empty_files(tmp_path, suffix, hint):
    name = f"empty.{suffix}"
    (tmp_path / name).touch()
    (artifact,) = fingerprint_input(tmp_path, declaration(name)).artifacts
    assert artifact.size == 0 and artifact.digest == hashlib.sha256(b"").hexdigest()
    assert artifact.format_hint == hint


def test_static_selection_and_nested_file(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/train.csv").write_bytes(b"1,2\n")
    (static,) = discover_inputs(
        'import pandas as pd\npd.read_csv("data/train.csv")',
        source_reference="train.py",
    ).artifacts
    (artifact,) = fingerprint_input(tmp_path, static).artifacts
    assert artifact.origin is artifact.content_origin is O.STATIC
    assert artifact.reference == artifact.name == "data/train.csv"


def test_missing_and_missing_parent(tmp_path):
    for reference in ("missing.csv", "missing/data.csv"):
        assert (
            code(fingerprint_input(tmp_path, declaration(reference))) == "input_missing"
        )


def test_symlink_file_and_parent_are_rejected(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "real/data.csv").write_bytes(b"private")
    (tmp_path / "link.csv").symlink_to("real/data.csv")
    (tmp_path / "link").symlink_to("real", target_is_directory=True)
    (tmp_path / "broken").symlink_to("missing")
    for reference in ("link.csv", "link/data.csv", "broken"):
        assert (
            code(fingerprint_input(tmp_path, declaration(reference))) == "input_symlink"
        )


def test_directories_regular_parent_fifo_socket(tmp_path):
    (tmp_path / "directory").mkdir()
    (tmp_path / "file").touch()
    os.mkfifo(tmp_path / "fifo")
    with tempfile.TemporaryDirectory(prefix="apizr-261-", dir="/tmp") as short:
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(Path(short) / "socket"))
            assert (
                code(fingerprint_input(Path(short), declaration("socket")))
                == "input_not_regular"
            )
        for reference in ("directory", "file/data.csv", "fifo"):
            assert (
                code(fingerprint_input(tmp_path, declaration(reference)))
                == "input_not_regular"
            )


def test_oversize_does_not_read(tmp_path, monkeypatch):
    (tmp_path / "data.csv").write_bytes(b"12345")

    def forbidden(*args):
        pytest.fail("Oversized input read")

    monkeypatch.setattr(inputs.os, "read", forbidden)
    assert (
        code(
            fingerprint_input(
                tmp_path, declaration(), policy=FingerprintPolicy(max_file_bytes=4)
            )
        )
        == "input_too_large"
    )


def test_growing_stream_is_bounded(tmp_path, monkeypatch):
    (tmp_path / "data.csv").write_bytes(b"1234")
    real_read = os.read
    reads = []

    def grow(fd, size):
        reads.append(size)
        if len(reads) == 1:
            (tmp_path / "data.csv").write_bytes(b"12345")
        return real_read(fd, size)

    monkeypatch.setattr(inputs.os, "read", grow)
    assert (
        code(
            fingerprint_input(
                tmp_path, declaration(), policy=FingerprintPolicy(max_file_bytes=4)
            )
        )
        == "input_too_large"
    )
    assert reads == [5]


@pytest.mark.parametrize(
    "attribute", ["st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"]
)
def test_changed_during_read_discards_digest(tmp_path, monkeypatch, attribute):
    (tmp_path / "data.csv").write_bytes(b"1234")
    real_stat = os.fstat
    calls = 0

    def changed(fd):
        nonlocal calls
        original = real_stat(fd)
        calls += 1
        if calls == 2:
            values = {
                name: getattr(original, name)
                for name in (
                    "st_dev",
                    "st_ino",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                    "st_mode",
                )
            }
            values[attribute] += 1
            return SimpleNamespace(**values)
        return original

    monkeypatch.setattr(inputs.os, "fstat", changed)
    assert (
        code(fingerprint_input(tmp_path, declaration())) == "input_changed_during_read"
    )


def test_short_read_discards_digest(tmp_path, monkeypatch):
    (tmp_path / "data.csv").write_bytes(b"1234")
    monkeypatch.setattr(inputs.os, "read", lambda *args: b"")
    assert (
        code(fingerprint_input(tmp_path, declaration())) == "input_changed_during_read"
    )


def test_replaced_path_discards_digest(tmp_path, monkeypatch):
    target = tmp_path / "data.csv"
    target.write_bytes(b"1234")
    real_stat = os.stat
    calls = 0

    def changed(path, *args, **kwargs):
        nonlocal calls
        original = real_stat(path, *args, **kwargs)
        if path == "data.csv":
            calls += 1
            if calls == 2:
                values = {
                    name: getattr(original, name)
                    for name in (
                        "st_dev",
                        "st_ino",
                        "st_size",
                        "st_mtime_ns",
                        "st_ctime_ns",
                        "st_mode",
                    )
                }
                values["st_ino"] += 1
                return SimpleNamespace(**values)
        return original

    monkeypatch.setattr(inputs.os, "stat", changed)
    assert (
        code(fingerprint_input(tmp_path, declaration())) == "input_changed_during_read"
    )


def test_replaced_special_descriptor_rejected(tmp_path, monkeypatch):
    import stat

    (tmp_path / "data.csv").touch()
    monkeypatch.setattr(
        inputs.os, "fstat", lambda fd: SimpleNamespace(st_mode=stat.S_IFIFO)
    )
    assert code(fingerprint_input(tmp_path, declaration())) == "input_not_regular"


@pytest.mark.parametrize(
    "error,expected",
    [
        (errno.ENOENT, "input_missing"),
        (errno.ELOOP, "input_symlink"),
        (errno.ENOTDIR, "input_not_regular"),
        (errno.EACCES, "input_unreadable"),
        (None, "input_unreadable"),
    ],
)
def test_os_errors_are_redacted(tmp_path, monkeypatch, error, expected):
    def fail(*args, **kwargs):
        raise OSError(error, "sensitive error /Users/private/data.csv")

    monkeypatch.setattr(inputs.os, "open", fail)
    result = fingerprint_input(tmp_path, declaration())
    assert code(result) == expected
    assert "private" not in result.model_dump_json()


def test_hard_links_and_metadata_do_not_change_identity(tmp_path):
    first, second = tmp_path / "A", tmp_path / "B"
    first.mkdir()
    second.mkdir()
    path = first / "data.csv"
    path.write_bytes(b"1234")
    (second / "data.csv").hardlink_to(path)
    a = fingerprint_input(first, declaration())
    path.chmod(0o600)
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    b = fingerprint_input(second, declaration())
    assert a == b
    assert "st_ino" not in a.model_dump_json()


def test_unverified_claims_are_not_trusted(tmp_path):
    (tmp_path / "data.csv").write_bytes(b"actual bytes")
    claim = InputArtifact(
        name="training",
        reference="data.csv",
        digest="a" * 64,
        size=999,
        origin=O.DECLARED,
    )
    (artifact,) = fingerprint_input(tmp_path, claim).artifacts
    assert artifact.digest == hashlib.sha256(b"actual bytes").hexdigest()
    assert artifact.size == 12 and artifact.content_origin is O.STATIC
    (tmp_path / "data.csv").unlink()
    assert code(fingerprint_input(tmp_path, claim)) == "input_missing"


def test_remote_is_never_opened_and_never_trusts_declared_hash(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Remote I/O")

    monkeypatch.setattr(inputs.os, "open", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    declared = parse_input_declaration("training=s3://bucket/train.parquet")
    result = fingerprint_input(tmp_path, declared)
    assert code(result) == "remote_content_unverified"
    assert result.artifacts[0].origin is O.DECLARED
    claim = result.artifacts[0].model_copy(
        update={"digest": "a" * 64, "size": 3, "content_origin": O.DECLARED}
    )
    assert code(fingerprint_input(tmp_path, claim)) == "remote_content_unverified"


def test_nonreference_and_runtime_selection(tmp_path):
    assert (
        code(
            fingerprint_input(tmp_path, InputArtifact(name="unknown", origin=O.STATIC))
        )
        == "unsupported_input_reference"
    )
    with pytest.raises(ValueError, match="explicit_input_invalid"):
        fingerprint_input(tmp_path, InputArtifact(name="observed", origin=O.RUNTIME))


def test_batch_order_multiple_names_and_admission_before_io(tmp_path, monkeypatch):
    (tmp_path / "data.csv").write_bytes(b"identical")
    declarations = (declaration(name="train"), declaration(name="validation"))
    result = fingerprint_inputs(tmp_path, declarations)
    assert len(result.artifacts) == 2
    assert result.artifacts[0].digest == result.artifacts[1].digest
    assert fingerprint_inputs(tmp_path, declarations[::-1]) == result
    assert fingerprint_inputs(tmp_path, ()).artifacts == ()

    def forbidden(*args, **kwargs):
        pytest.fail("invalid batch read data")

    monkeypatch.setattr(inputs.os, "open", forbidden)
    for selections in ((declarations[0],) * 2, (declarations[0],) * 257):
        with pytest.raises(ValueError):
            fingerprint_inputs(tmp_path, selections)
    with pytest.raises(ValueError):
        fingerprint_inputs(
            tmp_path,
            declarations,
            policy=FingerprintPolicy.model_construct(max_file_bytes=2**50),
        )


@pytest.mark.parametrize("limit", [0, -1, 1024**4 + 1, True, 1.5])
def test_policy_bounds(limit):
    with pytest.raises(ValueError):
        FingerprintPolicy(max_file_bytes=limit)


def test_dataset_ab_changes_plan_only(tmp_path):
    fixture = Path(__file__).parents[1] / "fixtures/experiments/inputs"
    source = (fixture / "train.py").read_bytes()
    subject = SourceIdentity(
        kind="python",
        reference="train.py",
        digest=hashlib.sha256(source).hexdigest(),
        module="train",
        capability_id="python:train:train",
    )
    (selection,) = discover_inputs(source, source_reference="train.py").artifacts
    (tmp_path / "data").mkdir()
    data_path = tmp_path / "data/train.csv"
    data_path.write_bytes((fixture / "data/train.csv").read_bytes())

    def plan():
        return ExperimentPlan(
            subject=subject,
            execution=ExecutionIntent(kind="training"),
            inputs=fingerprint_input(tmp_path, selection).artifacts,
        )

    a = plan()
    data_path.write_bytes(data_path.read_bytes().replace(b"0.25", b"0.75"))
    b = plan()
    assert a.subject == b.subject
    assert a.subject.capability_id == b.subject.capability_id
    assert a.execution == b.execution and a.parameters == b.parameters
    assert a.inputs[0].reference == b.inputs[0].reference == "data/train.csv"
    assert a.inputs[0].digest != b.inputs[0].digest
    assert plan_digest(a) != plan_digest(b)


@given(st.binary(max_size=4096))
@settings(max_examples=20, deadline=None)
def test_bounded_byte_identity_properties(data):
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        a, b = root / "A", root / "B"
        a.mkdir()
        b.mkdir()
        (a / "data.csv").write_bytes(data)
        (b / "data.csv").write_bytes(data)
        first = fingerprint_input(a, declaration())
        assert first == fingerprint_input(b, declaration())
        assert str(root) not in first.model_dump_json()
        changed = bytes([data[0] ^ 1]) + data[1:] if data else b"x"
        (b / "data.csv").write_bytes(changed)
        assert (
            first.artifacts[0].digest
            != fingerprint_input(b, declaration()).artifacts[0].digest
        )
        subject = SourceIdentity(kind="python", reference="train.py", digest="a" * 64)
        selected = fingerprint_inputs(
            a, (declaration(name="train"), declaration(name="validation"))
        ).artifacts
        p = ExperimentPlan(
            subject=subject, execution=ExecutionIntent(kind="train"), inputs=selected
        )
        q = ExperimentPlan(
            subject=subject,
            execution=ExecutionIntent(kind="train"),
            inputs=selected[::-1],
        )
        assert plan_bytes(p) == plan_bytes(q)


def test_mixed_invalid_batch_rejected_before_io(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Partially read an invalid batch")

    monkeypatch.setattr(inputs.os, "open", forbidden)
    with pytest.raises(ValueError, match="explicit_input_invalid"):
        fingerprint_inputs(
            tmp_path, (declaration(), InputArtifact(name="z", origin=O.RUNTIME))
        )


def test_path_disappears_after_read_is_mutation(tmp_path, monkeypatch):
    (tmp_path / "data.csv").write_bytes(b"1234")
    real_stat = os.stat
    calls = 0

    def missing(path, *args, **kwargs):
        nonlocal calls
        if path == "data.csv":
            calls += 1
            if calls == 2:
                raise FileNotFoundError(errno.ENOENT, "private path")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(inputs.os, "stat", missing)
    assert (
        code(fingerprint_input(tmp_path, declaration())) == "input_changed_during_read"
    )
