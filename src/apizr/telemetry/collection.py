"""Bounded process-local counters, isolated from experiment evidence and transport."""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Mapping
from contextvars import ContextVar, Token
from types import TracebackType
from typing import Literal
from weakref import WeakSet

from apizr.telemetry.consent import decision

OPERATIONS = frozenset(
    {
        "inspect",
        "history_list",
        "history_show",
        "history_diff",
        "capture_session",
        "generate_rest",
        "generate_mcp",
    }
)
OUTCOMES = frozenset({"success", "refused", "failed"})
_ACTIVE: ContextVar[UsageCapture | None] = ContextVar(
    "apizr_usage_capture", default=None
)
_LIVE: WeakSet[UsageCapture] = WeakSet()
_LOCK = threading.RLock()


class UsageCapture:
    def __init__(
        self,
        *,
        context: Literal["cli", "sdk", "vscode"] = "sdk",
        environ: Mapping[str, str] | None = None,
    ):
        self.context: Literal["cli", "sdk", "vscode"] = context
        self.environ = os.environ if environ is None else environ
        self._counts: dict[tuple[str, str], int] = {}
        self._total = 0
        self._token: Token[UsageCapture | None] | None = None
        self._owner = threading.get_ident()
        self._closed = False

    def __enter__(self) -> UsageCapture:
        with _LOCK:
            if len(_LIVE) < 32 and not self._closed and self._token is None:
                _LIVE.add(self)
                self._token = _ACTIVE.set(self)
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        with _LOCK:
            if self._token is not None:
                _ACTIVE.reset(self._token)
                self._token = None
            self.clear()
            self._closed = True
            _LIVE.discard(self)

    def clear(self) -> None:
        self._counts.clear()
        self._total = 0

    def record(self, operation: str, outcome: str) -> None:
        try:
            with _LOCK:
                if not decision(environ=self.environ).enabled:
                    self.clear()
                    return
                if (
                    self._closed
                    or threading.get_ident() != self._owner
                    or self._total >= 1000
                    or type(operation) is not str
                    or type(outcome) is not str
                    or operation not in OPERATIONS
                    or outcome not in OUTCOMES
                ):
                    return
                key = operation, outcome
                self._counts[key] = self._counts.get(key, 0) + 1
                self._total += 1
        except Exception:
            self.clear()

    def preview(self) -> dict[str, object]:
        from apizr.telemetry.model import UsageEvent, UsageReport, report_bytes
        from apizr.telemetry.preview import preview

        with _LOCK:
            result = preview(context=self.context, environ=self.environ)
            if not result["collection_enabled"] or self._closed:
                self.clear()
            report = UsageReport(
                schema_version="apizr.telemetry/v1",
                context=self.context,
                events=tuple(
                    UsageEvent.model_validate(
                        {"operation": operation, "outcome": outcome, "count": count},
                        strict=True,
                    )
                    for (operation, outcome), count in sorted(self._counts.items())
                ),
            )
            result["payload"] = report_bytes(report).decode().rstrip("\n")
            return result


def capture(
    *,
    context: Literal["cli", "sdk", "vscode"] = "sdk",
    environ: Mapping[str, str] | None = None,
) -> UsageCapture:
    return UsageCapture(context=context, environ=environ)


def discard_all() -> None:
    with _LOCK:
        for collector in _LIVE:
            collector.clear()


def observe(operation: str, outcome: str) -> None:
    """The computation boundary: a collection failure cannot change its outcome."""
    try:
        active = _ACTIVE.get()
        if active is not None:
            active.record(operation, outcome)
    except Exception:
        pass


def emit_preview(collector: UsageCapture) -> None:
    """Explicit local stderr preview only, never a sender or persistent queue."""
    try:
        if collector.environ.get("APIZR_TELEMETRY_PREVIEW") == "1":
            import json

            print(
                "APIZR_TELEMETRY_PREVIEW "
                + json.dumps(collector.preview(), separators=(",", ":")),
                file=sys.stderr,
            )
    except Exception:
        pass
