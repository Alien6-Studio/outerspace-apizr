"""Present local telemetry status and the public receiving-contract preview."""

import argparse
import json
import sys
from typing import Sequence

from apizr.telemetry.preview import preview


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="apizr telemetry")
    parser.add_argument("action", choices=("status", "preview"))
    args = parser.parse_args(argv)
    try:
        result = preview()
    except ValueError:
        print("apizr: invalid_telemetry_test_endpoint", file=sys.stderr)
        return 2
    if args.action == "status":
        result.pop("payload")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0
