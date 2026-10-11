"""Output observations reuse the secure file reader without interpreting contents."""

import errno
import hashlib
import os
import socket
import stat
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
    FingerprintPolicy,
    OutputCaptureResult,
    OutputDeclaration,
    _files,
    fingerprint_output,
    fingerprint_outputs,
)


def selection(reference="model.joblib", name="model", **kwargs):
    return OutputDeclaration(name=name, reference=reference, **kwargs)


def failure(result, code):
    assert result.artifacts == ()
    assert result.diagnostics[0].code == code
    assert "digest" not in result.model_dump_json()


@pytest.mark.parametrize(
    "content", [b"", b"opaque-model-sentinel\x00\xff\r\n", b"not a valid pickle"]
)
def test_exact_bytes_streamed_without_content_leak(
    tmp_path, monkeypatch, capsys, content
):
    (tmp_path / "model.joblib").write_bytes(content)
    (tmp_path / "neighbor").write_bytes(b"not selected")
    monkeypatch.setattr(_files, "_CHUNK_BYTES", 3)
    original_read, original_open = os.read, os.open
    reads = []
    opened = []

    def read(fd, count):
        reads.append(count)
        return original_read(fd, count)

    def open_file(path, flags, *args, **kwargs):
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)
        if not flags & os.O_DIRECTORY:
            opened.append(path)
            assert path == "model.joblib"
            assert flags & os.O_NOFOLLOW and flags & os.O_NONBLOCK
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "read", read)
    monkeypatch.setattr(os, "open", open_file)
    result = fingerprint_output(
        tmp_path, selection(media_type="application/octet-stream")
    )
    assert not result.diagnostics
    artifact = result.artifacts[0]
    assert artifact.digest == hashlib.sha256(content).hexdigest()
    assert artifact.size == len(content) and artifact.reference == "model.joblib"
    assert (
        artifact.origin is O.RUNTIME
        and artifact.media_type == "application/octet-stream"
    )
    assert opened == ["model.joblib"] and all(n <= 3 for n in reads)
    assert "opaque-model-sentinel" not in result.model_dump_json() + str(
        capsys.readouterr()
    )
    assert str(tmp_path) not in result.model_dump_json()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["model.joblib", "neighbor"]


@pytest.mark.parametrize("reference", ["missing", "missing/model.joblib"])
def test_missing_output_has_no_artifact(tmp_path, reference):
    failure(fingerprint_output(tmp_path, selection(reference)), "output_missing")


def test_symlink_and_parent_never_followed(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "real/model.joblib").write_bytes(b"private")
    (tmp_path / "model.joblib").symlink_to("real/model.joblib")
    (tmp_path / "linked").symlink_to("real")
    (tmp_path / "broken").symlink_to("missing")
    for reference in ("model.joblib", "linked/model.joblib", "broken"):
        failure(fingerprint_output(tmp_path, selection(reference)), "output_symlink")


def test_symlink_swap_after_admission_never_reads(tmp_path, monkeypatch):
    target = tmp_path / "model.joblib"
    target.write_bytes(b"admitted")
    (tmp_path / "secret").write_bytes(b"never-read")
    original = os.open
    reads = []

    def swapped(path, flags, *args, **kwargs):
        if path == "model.joblib":
            target.unlink()
            target.symlink_to("secret")
        return original(path, flags, *args, **kwargs)

    def read(fd, count):
        reads.append(fd)
        return b""

    monkeypatch.setattr(os, "open", swapped)
    monkeypatch.setattr(os, "read", read)
    result = fingerprint_output(tmp_path, selection())
    assert reads == []
    failure(result, "output_symlink")


def test_directory_fifo_socket_and_bad_parent_refused(tmp_path):
    (tmp_path / "directory").mkdir()
    (tmp_path / "file").touch()
    os.mkfifo(tmp_path / "fifo")
    for reference in ("directory", "fifo", "file/child"):
        failure(
            fingerprint_output(tmp_path, selection(reference)), "output_not_regular"
        )
    with tempfile.TemporaryDirectory(prefix="apizr-263-", dir="/tmp") as directory:
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(Path(directory) / "socket"))
            failure(
                fingerprint_output(Path(directory), selection("socket")),
                "output_not_regular",
            )


def test_replaced_device_descriptor_refused(tmp_path, monkeypatch):
    (tmp_path / "model.joblib").touch()
    monkeypatch.setattr(os, "fstat", lambda fd: SimpleNamespace(st_mode=stat.S_IFCHR))
    failure(fingerprint_output(tmp_path, selection()), "output_not_regular")


def test_size_refusal_before_read_and_growth_limit(tmp_path, monkeypatch):
    path = tmp_path / "model.joblib"
    path.write_bytes(b"12345")

    def forbidden(*args):
        pytest.fail("oversized output was read")

    with monkeypatch.context() as patch:
        patch.setattr(os, "read", forbidden)
        failure(
            fingerprint_output(
                tmp_path, selection(), policy=FingerprintPolicy(max_file_bytes=4)
            ),
            "output_too_large",
        )
    path.write_bytes(b"1234")
    original = os.read
    sizes = []

    def growing(fd, count):
        sizes.append(count)
        path.write_bytes(b"12345")
        return original(fd, count)

    monkeypatch.setattr(os, "read", growing)
    failure(
        fingerprint_output(
            tmp_path, selection(), policy=FingerprintPolicy(max_file_bytes=4)
        ),
        "output_too_large",
    )
    assert sizes == [5]


@pytest.mark.parametrize("change", ["rewrite", "replace", "remove", "truncate"])
def test_changed_during_read_discards_digest(tmp_path, monkeypatch, change):
    target = tmp_path / "model.joblib"
    target.write_bytes(b"initial bytes")
    original = os.read
    changed = False

    def read(fd, count):
        nonlocal changed
        data = original(fd, count)
        if data and not changed:
            changed = True
            if change == "rewrite":
                target.write_bytes(b"new bytes now")
            elif change == "replace":
                replacement = tmp_path / "replacement"
                replacement.write_bytes(b"initial bytes")
                replacement.replace(target)
            elif change == "remove":
                target.unlink()
            else:
                target.write_bytes(b"")
        return data

    monkeypatch.setattr(os, "read", read)
    failure(fingerprint_output(tmp_path, selection()), "output_changed_during_read")


@pytest.mark.parametrize(
    "error,code",
    [
        (errno.ENOENT, "output_missing"),
        (errno.ELOOP, "output_symlink"),
        (errno.ENOTDIR, "output_not_regular"),
        (errno.EACCES, "output_unreadable"),
        (None, "output_unreadable"),
    ],
)
def test_os_errors_are_redacted(tmp_path, monkeypatch, error, code):
    def fail(*args, **kwargs):
        raise OSError(error, "/private/sensitive/model")

    monkeypatch.setattr(os, "open", fail)
    result = fingerprint_output(tmp_path, selection())
    failure(result, code)
    assert (
        "private" not in result.model_dump_json()
        and "sensitive" not in result.model_dump_json()
    )


def test_batch_names_order_and_partial_failure(tmp_path):
    (tmp_path / "model.joblib").write_bytes(b"one file two names")
    a, b = selection(name="a"), selection(name="b")
    result = fingerprint_outputs(tmp_path, (b, a, selection("missing", name="c")))
    assert [x.name for x in result.artifacts] == ["a", "b"]
    assert result.artifacts[0].digest == result.artifacts[1].digest
    assert result.diagnostics[0].name == "c"
    assert fingerprint_outputs(tmp_path, (a, b)) == fingerprint_outputs(
        tmp_path, (b, a)
    )
    assert fingerprint_outputs(tmp_path, ()) == OutputCaptureResult()


def test_whole_selection_revalidated_before_io(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid selection performed I/O")

    monkeypatch.setattr(os, "open", forbidden)
    for selections in (
        [selection()],
        (selection(),) * 257,
        (selection(), selection()),
        (selection(), selection().model_copy(update={"reference": "../secret"})),
        (OutputDeclaration.model_construct(name="x", reference="/private"),),
    ):
        with pytest.raises(ValueError, match="^output_selection_invalid$"):
            fingerprint_outputs(tmp_path, selections)
    for policy in (
        FingerprintPolicy.model_construct(max_file_bytes=2**50),
        FingerprintPolicy().model_copy(update={"max_file_bytes": True}),
    ):
        with pytest.raises(ValueError, match="^output_selection_invalid$"):
            fingerprint_output(tmp_path, selection(), policy=policy)
    with pytest.raises(ValueError, match="^output_selection_invalid$"):
        fingerprint_output(
            tmp_path, selection().model_copy(update={"digest": "a" * 64})
        )


@given(st.binary(max_size=4096))
@settings(max_examples=25, deadline=None)
def test_relocation_and_byte_change_properties(content):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        a, b = root / "A", root / "B"
        a.mkdir()
        b.mkdir()
        for folder in (a, b):
            (folder / "artifacts").mkdir()
            (folder / "artifacts/model.joblib").write_bytes(content)
        selected = selection("artifacts/model.joblib")
        first = fingerprint_output(a, selected)
        assert first == fingerprint_output(b, selected)
        assert str(root) not in first.model_dump_json()
        changed = bytes([content[0] ^ 1]) + content[1:] if content else b"x"
        (b / "artifacts/model.joblib").write_bytes(changed)
        assert (
            fingerprint_output(b, selected).artifacts[0].digest
            != first.artifacts[0].digest
        )
