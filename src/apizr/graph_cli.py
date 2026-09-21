"""Single-discovery graph command; no transport or runtime imports."""

import argparse
import sys
from collections.abc import Sequence

from apizr.graph import graph_bytes, graph_repository
from apizr.graph.reporting import envelope_bytes, text_report
from apizr.repository_cli import (
    add_graph_arguments,
    add_scan_arguments,
    graph_policy,
    scan_policy,
)


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr graph",
        description="Build conservative static capability relationships without executing source.",
    )
    add_scan_arguments(parser)
    add_graph_arguments(parser)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--format", choices=["text", "json"], default="text")
    output.add_argument(
        "--graph", action="store_true", help="Emit canonical apizr.graph/v1 JSON only"
    )
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = graph_repository(
            args.root, scan_policy=scan_policy(args), graph_policy=graph_policy(args)
        )
    except (OSError, ValueError, UnicodeError, RecursionError):
        print(
            "apizr graph: invalid policy/input or inaccessible repository root; check roots, limits and filesystem support",
            file=sys.stderr,
        )
        return 2
    if args.graph:
        sys.stdout.buffer.write(graph_bytes(result.graph))
    elif args.format == "json":
        sys.stdout.buffer.write(envelope_bytes(result.graph))
    else:
        print(text_report(result.graph, details=args.details), end="")
    return result.graph.exit_code
