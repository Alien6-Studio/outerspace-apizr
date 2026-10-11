"""Explicit bounded evidence, serialized writers, no paths in portable results."""

import hashlib
import json
import os
from pathlib import Path

from pydantic import BaseModel

from apizr.extension_runtime.protocol import unique_object
from apizr.plugins.local.store import atomic_write, private_directory
from apizr.workspace.files import read_regular

from .models import destination_key

MAX_EVIDENCE_BYTES = 1048576


class EvidenceError(Exception):
    """Fixed evidence refusal, never expose file contents or paths."""


def read(path: Path) -> bytes:
    raw = read_regular(path, MAX_EVIDENCE_BYTES)
    try:
        json.loads(raw, object_pairs_hook=unique_object)
    except (ValueError, RecursionError):
        raise EvidenceError() from None
    return raw


def write_once(path: Path, value: BaseModel) -> None:
    raw = value.model_dump_json(by_alias=True).encode()
    if os.path.lexists(path):
        if json.loads(read(path)) != json.loads(raw):
            raise EvidenceError()
    else:
        with open(path, "xb", opener=lambda p, f: os.open(p, f, 0o600)) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())


def directory(root: Path, destination: str) -> Path:
    child = root / hashlib.sha256(destination_key(destination).encode()).hexdigest()
    private_directory(child)
    return child


def checkpoint(root: Path, value: BaseModel) -> None:
    raw = value.model_dump_json(by_alias=True).encode()
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise EvidenceError()
    path = root / "batch.json"
    if os.path.lexists(path):
        read(path)  # Refuse a redirected or non-regular file before replacement.
    atomic_write(path, raw)
