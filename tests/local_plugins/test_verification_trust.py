"""Operator identity captures public trust bytes without following filesystem aliases."""

import hashlib
import json
import os

import pytest

from apizr.contracts.publication import Tool
from apizr.workspace.verification import (
    capture_verification,
    trust_files,
    trust_identity,
)


def test_trust_identity_is_deterministic_and_sensitive_to_names_and_contents(tmp_path):
    files = {
        "signer.pub": b"public",
        "trust.toml": b"policy",
        "tsa/one.crt": b"certificate",
    }
    for name, raw in files.items():
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(raw)
    expected = hashlib.sha256(
        (
            json.dumps(
                {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
    ).hexdigest()
    target = capture_verification(
        expected_signer="a" * 64,
        tool=Tool(executable="/native/attest", version="0.1.0", sha256="b" * 64),
        trust_store=str(tmp_path),
    )
    assert trust_files(tmp_path) == files
    assert target.trust_store_sha256 == expected
    assert trust_identity(dict(reversed(list(files.items())))) == expected
    assert trust_identity(files | {"signer.pub": b"different"}) != expected
    assert (
        trust_identity({name.replace("one", "two"): raw for name, raw in files.items()})
        != expected
    )
    assert (
        trust_identity(
            {name: raw for name, raw in files.items() if name != "trust.toml"}
        )
        != expected
    )


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "root-link",
        "ancestor-link",
        "file-link",
        "tsa-link",
        "tsa-file",
        "private",
        "unknown",
        "tsa-unknown",
        "fifo",
        "directory",
        "file-size",
        "total-size",
        "count",
    ],
)
def test_trust_capture_rejects_unbounded_or_nonpublic_files(tmp_path, fault):
    root = tmp_path / "trust"
    if fault != "missing":
        root.mkdir()
    (tmp_path / "outside").write_text("public")
    if fault in {"root-link", "ancestor-link"}:
        link = tmp_path / "alias"
        link.symlink_to(root, target_is_directory=True)
        if fault == "ancestor-link":
            (root / "inner").mkdir()
            root = link / "inner"
        else:
            root = link
    if fault == "file-link":
        (root / "signer.pub").symlink_to(tmp_path / "outside")
    if fault == "tsa-link":
        (root / "tsa").symlink_to(tmp_path, target_is_directory=True)
    if fault == "tsa-file":
        (root / "tsa").write_text("public")
    if fault == "private":
        (root / "signer.pub").write_bytes(b"PRIVATE KEY sentinel")
    if fault == "unknown":
        (root / "secret.key").write_text("secret")
    if fault == "tsa-unknown":
        (root / "tsa").mkdir()
        (root / "tsa/signer.pub").write_text("public")
    if fault == "fifo":
        os.mkfifo(root / "signer.pub")
    if fault == "directory":
        (root / "signer.pub").mkdir()
    if fault == "file-size":
        (root / "signer.pub").write_bytes(b"x" * (1048576 + 1))
    if fault == "total-size":
        for index in range(5):
            (root / f"{index}.pub").write_bytes(b"x" * 1048576)
    if fault == "count":
        for index in range(129):
            (root / f"{index}.pub").write_bytes(b"")
    with pytest.raises((OSError, ValueError)):
        trust_files(root)
