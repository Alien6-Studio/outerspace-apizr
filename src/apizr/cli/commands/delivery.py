"""JSON-only batch delivery and explicit resume, backed by the Python coordinator."""

import argparse
import json
import signal
import sys
from pathlib import Path
from threading import Event
from typing import Sequence

from apizr.delivery_batch import BatchError, BatchRequest, deliver_batch
from apizr.extension_runtime import ExtensionError
from apizr.plugins.local import PluginError, read_arguments
from apizr.workspace.operator_policy import AuthorizationDenied, load_operator_policy
from apizr.workspace.user import plugins_directory


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="apizr delivery")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "resume"):
        command = commands.add_parser(name)
        command.add_argument("--request", type=Path, required=True)
        command.add_argument("--operator-policy", type=Path, required=True)
        command.add_argument("--plugins-dir", type=Path)
    args = parser.parse_args(argv)
    cancel = Event()
    previous = signal.getsignal(signal.SIGINT)
    try:
        request = BatchRequest.model_validate_json(
            json.dumps(read_arguments(args.request))
        )
        policy = load_operator_policy(args.operator_policy)
        signal.signal(signal.SIGINT, lambda *_: cancel.set())
        result = deliver_batch(
            request,
            resume=args.command == "resume",
            directory=plugins_directory(args.plugins_dir, None),
            operator_policy=policy,
            cancel=cancel,
        )
        print(result.model_dump_json(by_alias=True))
        return result.exit_code
    except (
        BatchError,
        PluginError,
        AuthorizationDenied,
        ExtensionError,
        ValueError,
        OSError,
    ):
        print("apizr delivery: batch_request_or_evidence_invalid", file=sys.stderr)
        return 2
    finally:
        signal.signal(signal.SIGINT, previous)
