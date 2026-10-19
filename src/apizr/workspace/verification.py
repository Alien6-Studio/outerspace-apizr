"""Bounded public trust snapshots for explicit operator verification authority."""

import hashlib
import json
import os
from pathlib import Path

from apizr.contracts.publication import Docker, Tool, VerificationTarget
from apizr.workspace.files import directory_fd, read_regular

MAX_TRUST_FILE_BYTES = 1048576
MAX_TRUST_BYTES = 4 * MAX_TRUST_FILE_BYTES
MAX_TRUST_FILES = 128


def trust_files(source: Path) -> dict[str, bytes]:
    """Read only public keys, native policy and TSA certificates, without symlinks."""
    files: dict[str, bytes] = {}
    total = 0
    for suffix in ("", "tsa/"):
        parent = source / "tsa" if suffix else source
        if suffix and not os.path.lexists(parent):
            continue
        with directory_fd(parent) as descriptor, os.scandir(descriptor) as entries:
            for entry in entries:
                if not suffix and entry.name == "tsa":
                    continue
                if len(files) >= MAX_TRUST_FILES or not (
                    Path(entry.name).suffix == (".crt" if suffix else ".pub")
                    or (not suffix and entry.name == "trust.toml")
                ):
                    raise ValueError("invalid_trust_store")
                raw = read_regular(
                    parent / entry.name,
                    min(MAX_TRUST_FILE_BYTES, MAX_TRUST_BYTES - total),
                )
                if b"PRIVATE KEY" in raw:
                    raise ValueError("invalid_trust_store")
                total += len(raw)
                files[suffix + entry.name] = raw
    return files


def trust_identity(files: dict[str, bytes]) -> str:
    """SHA-256 of a canonical relative-path to content-digest manifest."""
    manifest = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return hashlib.sha256(raw).hexdigest()


def capture_verification(
    *, expected_signer: str, tool: Tool, trust_store: str
) -> VerificationTarget:
    """Capture trusted operator choices; never call on behalf of an untrusted request."""
    return VerificationTarget(
        expected_signer=expected_signer,
        tool=tool,
        trust_store=Docker.absolute(trust_store),
        trust_store_sha256=trust_identity(
            trust_files(Path(Docker.absolute(trust_store)))
        ),
    )
