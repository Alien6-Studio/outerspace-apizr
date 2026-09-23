"""Dependency-free peer for the reusable apizr.extension/v1 invocation API."""

import json
import re
import sys

PROTOCOL = "apizr.extension/v1"
MAX_REQUEST_BYTES = 64 * 1024 * 1024


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError("Request too large")
        request = json.loads(raw.decode("utf-8"))
        if (
            not isinstance(request, dict)
            or set(request) != {"protocol", "request_id", "operation", "arguments"}
            or request["protocol"] != PROTOCOL
            or not isinstance(request["request_id"], str)
            or re.fullmatch(r"[0-9a-f]{32}", request["request_id"]) is None
            or not isinstance(request["operation"], str)
            or not isinstance(request["arguments"], dict)
        ):
            raise ValueError("Unsupported request")
        response = {
            key: request[key] for key in ("protocol", "request_id", "operation")
        }
        arguments = request["arguments"]
        if request["operation"] != "describe":
            response.update(
                status="error",
                error={"code": "unknown_operation", "message": "Unsupported operation"},
            )
        elif set(arguments) != {"source_digest"} or not isinstance(
            arguments["source_digest"], str
        ):
            response.update(
                status="error",
                error={
                    "code": "invalid_arguments",
                    "message": "Expected a source digest",
                },
            )
        else:
            response.update(
                status="ok",
                result={
                    "source_digest": arguments["source_digest"],
                    "message": "demo extension reached",
                },
            )
        print(json.dumps(response, separators=(",", ":")))
        return 0
    except (ValueError, TypeError, RecursionError):
        print("Unsupported extension request", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
