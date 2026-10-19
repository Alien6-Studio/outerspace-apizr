"""Closed, identifier-free aggregate usage payloads for future opt-in clients."""

import json
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apizr.contracts.json_budget import preflight_json

MAX_REPORT_BYTES = 16384
Context = Literal["cli", "sdk", "vscode"]
Operation = Literal[
    "inspect",
    "history_list",
    "history_show",
    "history_diff",
    "capture_session",
    "generate_rest",
    "generate_mcp",
]


class UsageEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, revalidate_instances="always"
    )

    operation: Operation
    outcome: Literal["success", "refused", "failed"]
    count: Annotated[int, Field(ge=1, le=1000)]


class UsageReport(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, revalidate_instances="always"
    )

    schema_version: Literal["apizr.telemetry/v1"]
    context: Context
    events: Annotated[tuple[UsageEvent, ...], Field(max_length=32)]

    @model_validator(mode="after")
    def bounded_aggregate(self) -> Self:
        keys = [(event.operation, event.outcome) for event in self.events]
        if len(set(keys)) != len(keys) or sum(e.count for e in self.events) > 1000:
            raise ValueError("telemetry_aggregate_limit")
        return self


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("telemetry_duplicate_key")
        result[key] = value
    return result


def decode_report(raw: bytes) -> UsageReport:
    """Admit bounded UTF-8 JSON before decoding; never include rejected values."""
    try:
        text = preflight_json(
            raw, max_bytes=MAX_REPORT_BYTES, max_nodes=512, max_depth=8
        )
        json.loads(text, object_pairs_hook=_unique)
        return UsageReport.model_validate_json(text, strict=True)
    except (ValueError, RecursionError):
        raise ValueError("invalid_telemetry_report") from None


def report_bytes(report: UsageReport) -> bytes:
    """Re-admit caller-supplied models, including constructed or copied values."""
    try:
        admitted = UsageReport.model_validate(report, strict=True)
    except ValueError:
        raise ValueError("invalid_telemetry_report") from None
    raw = admitted.model_dump_json().encode("utf-8") + b"\n"
    decode_report(raw)
    return raw
