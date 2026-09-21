"""Offline repository scan command; existing commands remain separate."""

import argparse
import sys
from collections.abc import Sequence

from apizr.repository import catalog_bytes, scan
from apizr.repository.reporting import envelope_bytes, text_report
from apizr.repository_cli import add_scan_arguments, scan_policy


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr scan",
        description="Statically inventory Python sources without imports, Git or network access.",
    )
    add_scan_arguments(parser)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--format", choices=["text", "json"], default="text")
    output.add_argument(
        "--catalog",
        action="store_true",
        help="Emit canonical apizr.catalog/v1 JSON only",
    )
    parser.add_argument(
        "--details", action="store_true", help="Expand the human report"
    )
    args = parser.parse_args(argv)
    try:
        catalog = scan(args.root, policy=scan_policy(args))
    except (OSError, ValueError, UnicodeError, RecursionError):
        print(
            "apizr scan: invalid policy or inaccessible repository root; check source roots, limits and filesystem support",
            file=sys.stderr,
        )
        return 2
    if args.catalog:
        sys.stdout.buffer.write(catalog_bytes(catalog))
    elif args.format == "json":
        sys.stdout.buffer.write(envelope_bytes(catalog))
    else:
        print(text_report(catalog, details=args.details), end="")
    return catalog.exit_code
