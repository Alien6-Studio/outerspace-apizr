"""Installed test peer for activation; never imported by the test host."""

import json
import os
import sys
import time
from pathlib import Path

request = json.load(sys.stdin)
args = request["arguments"]
if "marker" in args:
    Path(args["marker"]).write_text(str(os.getpid()))
if "wait" in args:
    time.sleep(args["wait"])
if args.get("fail"):
    print("PLUGIN-DIAGNOSTIC-SENTINEL", file=sys.stderr)
    sys.exit(7)
print(
    json.dumps(
        {
            **{key: request[key] for key in ("protocol", "request_id", "operation")},
            "status": "ok",
            "result": {"environment": dict(os.environ), "value": args.get("value")},
        }
    )
)
