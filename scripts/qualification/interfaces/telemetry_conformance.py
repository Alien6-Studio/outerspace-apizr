"""Qualify a disposable loopback collector with the public synthetic contract.

Never contact production or retain response bodies, headers or endpoint details.
This checks admission/framing only; private storage, expiry and deployment need
their own end-to-end evidence.
"""

import argparse
import hashlib
import ipaddress
import json
import socket
import time
from collections import Counter
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "tests/fixtures/telemetry/conformance.json"
SCHEMA = ROOT / "specs/apizr-telemetry-v1.schema.json"
MAX_BYTES = 16384


def endpoint(value):
    try:
        if len(value) > 128 or any(ord(c) <= 32 or ord(c) >= 127 for c in value):
            raise ValueError()
        url = urlsplit(value)
        if (
            url.scheme != "http"
            or not url.hostname
            or not ipaddress.ip_address(url.hostname).is_loopback
            or url.port is None
            or not 1 <= url.port <= 65535
            or url.path not in ("", "/")
            or url.query
            or url.fragment
            or url.username is not None
            or url.password is not None
        ):
            raise ValueError()
        return url.hostname, url.port
    except ValueError:
        raise ValueError("Expected an explicit HTTP loopback IP and port") from None


def cases(fixtures):
    for item in fixtures:
        raw = item["body"].encode("utf-8")
        yield (
            item["name"],
            raw,
            [str(len(raw))],
            "application/json",
            None,
            "/",
            False,
            204 if item["accepted"] else 400,
        )
    empty = fixtures[0]["body"].encode("utf-8")
    for name, raw, lengths, content_type, transfer, path, truncated, expected in (
        (
            "byte-boundary",
            empty + b" " * (MAX_BYTES - len(empty)),
            [str(MAX_BYTES)],
            "application/json",
            None,
            "/",
            False,
            204,
        ),
        (
            "oversized",
            b"x" * (MAX_BYTES + 1),
            [str(MAX_BYTES + 1)],
            "application/json",
            None,
            "/",
            False,
            413,
        ),
        ("empty", b"", ["0"], "application/json", None, "/", False, 413),
        ("invalid-utf8", b"\xff", ["1"], "application/json", None, "/", False, 400),
        ("missing-length", b"", [], "application/json", None, "/", False, 400),
        (
            "duplicate-length",
            b"{}",
            ["2", "2"],
            "application/json",
            None,
            "/",
            False,
            400,
        ),
        ("negative-length", b"", ["-1"], "application/json", None, "/", False, 400),
        ("nondecimal-length", b"", ["2x"], "application/json", None, "/", False, 400),
        (
            "huge-length",
            b"",
            ["999999999999999999999999"],
            "application/json",
            None,
            "/",
            False,
            413,
        ),
        (
            "transfer-encoding",
            b"{}",
            ["2"],
            "application/json",
            "chunked",
            "/",
            False,
            400,
        ),
        ("wrong-type", b"{}", ["2"], "text/plain", None, "/", False, 400),
        ("wrong-path", b"{}", ["2"], "application/json", None, "/other", False, 400),
        ("truncated", b"{}", ["9"], "application/json", None, "/", True, 400),
    ):
        yield name, raw, lengths, content_type, transfer, path, truncated, expected


def qualify(value, *, timeout: float = 3):
    host, port = endpoint(value)
    if not 0 < timeout <= 5:
        raise ValueError("Request timeout must be between 0 and 5 seconds")
    raw_corpus = CORPUS.read_bytes()
    fixtures = json.loads(raw_corpus)
    if not 1 <= len(fixtures) <= 48 or fixtures[0]["name"] != "empty-cli":
        raise ValueError("Unexpected public conformance corpus")
    results = []
    deadline = time.monotonic() + 60
    for name, raw, lengths, content_type, transfer, path, truncated, expected in cases(
        fixtures
    ):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            results.append(
                {"case": name, "result": "failed", "reason": "total_deadline"}
            )
            break
        connection = HTTPConnection(host, port, timeout=min(timeout, remaining))
        observed, reason = None, None
        try:
            connection.putrequest("POST", path, skip_accept_encoding=True)
            connection.putheader("Content-Type", content_type)
            for length in lengths:
                connection.putheader("Content-Length", length)
            if transfer:
                connection.putheader("Transfer-Encoding", transfer)
            connection.endheaders(raw)
            if truncated:
                assert connection.sock is not None
                connection.sock.shutdown(socket.SHUT_WR)
            response = connection.getresponse()
            observed = response.status
            if response.getheader("Content-Length") not in (None, "0") or response.read(
                1
            ):
                reason = "nonempty_response"
            elif observed != expected:
                reason = "unexpected_status"
        except (OSError, HTTPException, ValueError):
            reason = "transport_failure"
        finally:
            connection.close()
        results.append(
            {
                "case": name,
                "expected": expected,
                "observed": observed,
                "result": "passed" if reason is None else "failed",
                **({"reason": reason} if reason else {}),
            }
        )
    expected_counts = Counter()
    for item in fixtures:
        if item["accepted"]:
            report = json.loads(item["body"])
            for event in report["events"]:
                expected_counts[
                    (report["context"], event["operation"], event["outcome"])
                ] += event["count"]
    return {
        "schema": "apizr.telemetry-conformance/v1",
        "result": "passed"
        if all(r["result"] == "passed" for r in results)
        else "failed",
        "loopback_only": True,
        "corpus_sha256": hashlib.sha256(raw_corpus).hexdigest(),
        "public_schema_sha256": hashlib.sha256(SCHEMA.read_bytes()).hexdigest(),
        "checks": results,
        "expected_synthetic_counts": [
            {
                "context": context,
                "operation": operation,
                "outcome": outcome,
                "count": count,
            }
            for (context, operation, outcome), count in sorted(expected_counts.items())
        ],
        "private_storage_and_retention_qualified": False,
        "production_qualified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = qualify(args.endpoint)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"result": report["result"], "checks": len(report["checks"])}))
    raise SystemExit(0 if report["result"] == "passed" else 1)


if __name__ == "__main__":
    main()
