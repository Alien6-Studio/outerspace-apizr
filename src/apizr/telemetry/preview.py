"""Local report preview: explicit consent, no project reads, spool or sender."""

import ipaddress
from collections.abc import Mapping
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from apizr.telemetry.consent import decision

if TYPE_CHECKING:
    from apizr.telemetry.model import Context

PLANNED_ENDPOINT = "https://telemetry.outerspace.sh"


def _endpoint(environ: Mapping[str, str]) -> str:
    override = environ.get("APIZR_TELEMETRY_TEST_ENDPOINT")
    if override is None:
        return PLANNED_ENDPOINT
    try:
        if len(override) > 128 or any(
            ord(char) <= 32 or ord(char) >= 127 for char in override
        ):
            raise ValueError()
        parsed = urlsplit(override)
        if (
            parsed.scheme != "http"
            or parsed.hostname is None
            or not ipaddress.ip_address(parsed.hostname).is_loopback
            or parsed.port is None
            or not 1 <= parsed.port <= 65535
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError()
    except ValueError:
        raise ValueError("invalid_telemetry_test_endpoint") from None
    return override


def preview(
    *, context: "Context" = "cli", environ: Mapping[str, str] | None = None
) -> dict[str, object]:
    """Show an empty report outside an explicit process-local capture scope."""
    import os

    from apizr.telemetry.model import UsageReport, report_bytes

    env = os.environ if environ is None else environ
    consent = decision(environ=env)
    report = UsageReport(
        schema_version="apizr.telemetry/v1", context=context, events=()
    )
    return {
        "endpoint": _endpoint(env),
        "opt_in_requested": consent.requested,
        "context_allows": consent.context_allows,
        "collection_enabled": consent.enabled,
        "transmission_available": False,
        "reason": consent.reason,
        "payload": report_bytes(report).decode("utf-8").rstrip("\n"),
    }
