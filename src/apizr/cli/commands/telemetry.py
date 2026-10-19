"""Present local telemetry status and the public receiving-contract preview."""

import argparse
import json
import sys
from collections.abc import Callable, Sequence

from apizr.environment.extras import MissingExtra
from apizr.telemetry.collection import capture, emit_preview, observe
from apizr.telemetry.consent import disable, enable
from apizr.telemetry.preview import preview


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="apizr telemetry")
    parser.add_argument("action", choices=("status", "enable", "disable", "preview"))
    args = parser.parse_args(argv)
    try:
        if args.action == "enable":
            enable()
        elif args.action == "disable":
            disable()
        result = preview()
    except ValueError as error:
        code = str(error)
        if code not in {"invalid_telemetry_config", "invalid_telemetry_test_endpoint"}:
            code = "invalid_telemetry_config"
        print(f"apizr: {code}", file=sys.stderr)
        return 2
    if args.action != "preview":
        result.pop("payload")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


def run_command(argv: Sequence[str], execute: Callable[[], int]) -> int:
    """Keep all observation failures outside the command's outcome and output."""
    if not argv or argv[0] == "telemetry":
        return execute()
    operation = None
    if argv[0] == "inspect" or list(argv[:2]) == ["experiment", "inspect"]:
        operation = "inspect"
    elif (
        len(argv) > 1
        and argv[0] == "experiment"
        and argv[1] in {"list", "show", "diff"}
    ):
        operation = "history_" + argv[1]
    elif len(argv) > 1 and argv[0] == "generate" and argv[1] in {"rest", "mcp"}:
        operation = "generate_" + argv[1]
    try:
        import os

        collector = capture(
            context="vscode"
            if os.environ.get("APIZR_TELEMETRY_CONTEXT") == "vscode"
            else "cli"
        )
        collector.__enter__()
    except Exception:
        return execute()
    outcome = "failed"
    try:
        code = execute()
        outcome = "success" if code == 0 else "refused" if code == 2 else "failed"
        return code
    except MissingExtra:
        outcome = "refused"
        raise
    except SystemExit as error:
        outcome = "success" if error.code in (None, 0) else "refused"
        raise
    finally:
        try:
            if operation is not None:
                observe(operation, outcome)
            emit_preview(collector)
        except Exception:
            pass
        finally:
            try:
                collector.__exit__(None, None, None)
            except Exception:
                pass
