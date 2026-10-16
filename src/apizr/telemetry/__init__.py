"""Explicit local usage controls and bounded memory; no network client."""

from typing import TYPE_CHECKING

from apizr.telemetry.collection import capture
from apizr.telemetry.consent import disable, enable, status
from apizr.telemetry.preview import preview

if TYPE_CHECKING:
    from apizr.telemetry.model import (
        UsageEvent,
        UsageReport,
        decode_report,
        report_bytes,
    )

__all__ = [
    "UsageEvent",
    "UsageReport",
    "capture",
    "decode_report",
    "disable",
    "enable",
    "preview",
    "report_bytes",
    "status",
]


def __getattr__(name: str):
    if name in {"UsageEvent", "UsageReport", "decode_report", "report_bytes"}:
        from apizr.telemetry import model

        return getattr(model, name)
    raise AttributeError(name)
