"""One bounded JSON request/response over stdio; no daemon, editor SDK or UI."""

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from apizr.contracts.json import SizeExceeded, encode
from apizr.contracts.json_budget import preflight_json
from apizr.editor_contracts.model import EditorRequest
from apizr.extension_runtime.protocol import unique_object
from apizr.workspace.analysis_session import load_scope
from apizr.workspace.editor_session import execute, failure
from apizr.workspace.operator_policy import AuthorizationDenied, load_operator_policy


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="apizr editor")
    parser.add_argument(
        "--project",
        type=Path,
        help="Operator-selected apizr.toml; required for project operations",
    )
    parser.add_argument("--operator-policy", type=Path)
    parser.add_argument(
        "--store",
        default=".apizr/experiments/v1",
        help="Operator-selected store relative to the project root; requires its exact history.read grant",
    )
    args = parser.parse_args(argv)
    request = None
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            response = failure("request_too_large")
        else:
            data = json.loads(
                preflight_json(raw, max_bytes=65536, max_nodes=8192, max_depth=32),
                object_pairs_hook=unique_object,
            )
            request = EditorRequest.model_validate_json(json.dumps(data), strict=True)
            scope = None
            if request.operation != "capabilities" and args.project is not None:
                if not args.project.is_absolute() or (
                    args.operator_policy is not None
                    and not args.operator_policy.is_absolute()
                ):
                    raise ValueError()
                policy = (
                    load_operator_policy(args.operator_policy)
                    if args.operator_policy
                    else None
                )
                scope = load_scope(args.project, policy)
            response = execute(request, scope, store=args.store)
    except AuthorizationDenied as error:
        response = failure(error.code, request)
    except (OSError, ValueError, TypeError, RecursionError):
        response = failure("invalid_request", request)
    try:
        output = encode(response.model_dump(mode="json"), 4194304)
    except (SizeExceeded, ValueError, RecursionError):
        response = failure("response_too_large", request)
        output = encode(response.model_dump(mode="json"), 4194304)
    sys.stdout.buffer.write(output)
    try:
        from apizr.telemetry.collection import observe

        operation = {
            "inspect": "inspect",
            "experiment_list": "history_list",
            "experiment_show": "history_show",
            "experiment_diff": "history_diff",
        }.get(response.operation or "")
        if operation is not None:
            observe(operation, "success" if response.ok else "refused")
    except Exception:
        pass
    return 0 if response.ok else 2
