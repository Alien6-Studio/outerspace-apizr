"""Pure local report preview. No preferences, project reads, spool or sender."""

import ipaddress
import os
from collections.abc import Mapping
from urllib.parse import urlsplit

from apizr.telemetry.model import Context, UsageReport, report_bytes

PLANNED_ENDPOINT = "https://telemetry.outerspace.sh"


def _endpoint(environ: Mapping[str, str]) -> str:
    override = environ.get("APIZR_TELEMETRY_TEST_ENDPOINT")
    if override is None:
        return PLANNED_ENDPOINT
    try:
        parsed = urlsplit(override)
        if (
            len(override) > 128
            or any(ord(char) <= 32 or ord(char) >= 127 for char in override)
            or parsed.scheme != "http"
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
    *, context: Context = "cli", environ: Mapping[str, str] | None = None
) -> dict[str, object]:
    """Show the exact empty payload of this non-collecting release, even at opt-in."""
    env = os.environ if environ is None else environ
    requested = env.get("APIZR_TELEMETRY") == "1"
    ci = env.get("CI", "").lower() not in ("", "0", "false")
    host_allows = env.get("APIZR_TELEMETRY_ALLOWED", "1") == "1"
    report = UsageReport(
        schema_version="apizr.telemetry/v1", context=context, events=()
    )
    return {
        "endpoint": _endpoint(env),
        "opt_in_requested": requested,
        "context_allows": not ci and host_allows,
        "collection_enabled": False,
        "transmission_available": False,
        "reason": "production_unavailable",
        "payload": report_bytes(report).decode("utf-8").rstrip("\n"),
    }
