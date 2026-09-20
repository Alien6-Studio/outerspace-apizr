"""Canonical readiness bytes and digest, independent of IR canonical bytes."""

import json

from apizr.capabilities.model import Digest

from .model import ReadinessReport


def canonical_bytes(report: ReadinessReport) -> bytes:
    return (
        json.dumps(
            report.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def report_digest(report: ReadinessReport) -> Digest:
    return Digest.of_bytes(canonical_bytes(report))
