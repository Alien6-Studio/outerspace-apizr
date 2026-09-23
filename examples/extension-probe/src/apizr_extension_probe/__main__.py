"""Return a small JSON document without application or external side effects."""

import json
import sys


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if (
            not isinstance(request, dict)
            or set(request) != {"protocol", "request_id", "operation", "source_digest"}
            or request["protocol"] != "apizr.extension-probe/v1"
            or request["request_id"] != "packaging-proof"
            or request["operation"] != "describe"
            or not isinstance(request["source_digest"], str)
        ):
            raise ValueError("Unsupported extension request")
        print(
            json.dumps(
                {
                    "protocol": request["protocol"],
                    "request_id": request["request_id"],
                    "operation": request["operation"],
                    "result": {
                        "source_digest": request["source_digest"],
                        "message": "demo extension reached",
                    },
                }
            )
        )
    except (ValueError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
