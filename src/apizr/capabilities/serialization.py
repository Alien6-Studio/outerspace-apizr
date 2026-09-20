"""The single canonical JSON representation and its external digest."""

import json

from .model import CapabilityDocument, Digest


def canonical_bytes(document: CapabilityDocument) -> bytes:
    return (
        json.dumps(
            document.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def document_digest(document: CapabilityDocument) -> Digest:
    return Digest.of_bytes(canonical_bytes(document))
