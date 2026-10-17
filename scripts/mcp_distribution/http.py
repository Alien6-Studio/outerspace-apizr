"""Bounded GET-only provider access; credentials never enter reports or redirects."""

import json
import urllib.error
import urllib.parse
import urllib.request

from .providers import outcome

MAX_JSON = 8 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(
    url: str, *, token: str | None = None, limit: int = MAX_JSON
) -> tuple[bytes | None, dict | None]:
    target = urllib.parse.urlsplit(url)
    if target.scheme != "https" or target.username or target.password:
        return None, outcome(
            "mismatch", "Provider URL must use HTTPS without credentials"
        )
    if token and target.hostname not in {"glama.ai", "api.smithery.ai"}:
        return None, outcome(
            "mismatch", "Credential destination is not the intended provider"
        )
    headers = {
        "Accept": "application/json",
        "User-Agent": "apizr-distribution-verifier/0.4.6",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.build_opener(NoRedirect()).open(
            request, timeout=30
        ) as response:
            body = response.read(limit + 1)
            if len(body) > limit:
                return None, outcome(
                    "temporarily_unavailable",
                    "Provider response exceeds the configured bound",
                )
            return body, None
    except urllib.error.HTTPError as error:
        if error.code in {401, 403}:
            status = "authentication_required"
        elif error.code == 404:
            status = "missing"
        else:
            status = "temporarily_unavailable"
        # Never retain provider error bodies, request headers, tokens or exception text.
        return None, outcome(
            status, "Provider request did not return evidence", http_status=error.code
        )
    except (OSError, ValueError):
        return None, outcome(
            "temporarily_unavailable", "Provider request could not be completed"
        )


def fetch_json(
    url: str, *, token: str | None = None
) -> tuple[dict | None, dict | None]:
    body, error = fetch(url, token=token)
    if error:
        return None, error
    assert body is not None
    try:
        value = json.loads(body)
        if not isinstance(value, dict):
            raise ValueError
        return value, None
    except (ValueError, TypeError, RecursionError):
        return None, outcome(
            "temporarily_unavailable", "Provider returned invalid JSON evidence"
        )
