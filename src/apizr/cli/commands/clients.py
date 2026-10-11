"""Offline export and owned-tree regeneration, with fixed machine diagnostics."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from apizr.client_collections import (
    ClientError,
    canonical_bytes,
    export_client_collection,
)
from apizr.interfaces.serialization import json_bytes


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr clients",
        description="Export or safely regenerate local client collections from a REST bundle.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("export", "sync"):
        child = commands.add_parser(command)
        child.add_argument("--bundle", type=Path, required=True)
        child.add_argument(
            "--format", choices=("postman", "bruno", "insomnia"), required=True
        )
        child.add_argument("--output-dir", type=Path, required=True)
        child.add_argument("--base-url", default="http://127.0.0.1:8000")
        child.add_argument("--name", default="Apizr REST API")
    args = parser.parse_args(argv)
    try:
        result = export_client_collection(
            args.bundle,
            format=args.format,
            output_dir=args.output_dir,
            name=args.name,
            base_url=args.base_url,
            sync=args.command == "sync",
        )
        sys.stdout.buffer.write(canonical_bytes(result))
        return 0
    except ClientError as error:
        sys.stdout.buffer.write(
            json_bytes({"state": "refused", "diagnostic": str(error)})
        )
        return (
            1
            if str(error)
            in {
                "client_output_not_empty",
                "client_export_modified",
                "client_sync_conflict",
                "rest_bundle_changed",
            }
            else 2
        )
    except KeyboardInterrupt:
        return 130
