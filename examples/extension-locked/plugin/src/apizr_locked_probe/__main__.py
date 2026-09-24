"""Trusted demonstration of an installed plugin using a transitive dependency."""

import json
import sys

from apizr_locked_helper import answer

request = json.load(sys.stdin)
print(
    json.dumps(
        {
            "protocol": request["protocol"],
            "request_id": request["request_id"],
            "operation": request["operation"],
            "status": "ok",
            "result": {"answer": answer()},
        }
    )
)
