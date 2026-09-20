"""Single-discovery graph command; no transport or runtime imports."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from apizr.graph import GraphPolicy, graph_bytes, graph_repository
from apizr.graph.reporting import envelope_bytes, text_report
from apizr.repository import ScanPolicy


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr graph",
        description="Build conservative static capability relationships without executing source.",
    )
    parser.add_argument("root", type=Path)
    parser.add_argument(
        "--source-root",
        action="append",
        help="Relative source root; repeat for disjoint roots",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Additional excluded directory basename",
    )
    parser.add_argument("--max-file-bytes", type=int, default=1048576)
    parser.add_argument("--max-source-files", type=int, default=1000)
    parser.add_argument("--max-total-bytes", type=int, default=16777216)
    parser.add_argument("--max-entries", type=int, default=20000)
    parser.add_argument("--max-depth", type=int, default=64)
    parser.add_argument("--max-ast-nodes", type=int, default=500000)
    parser.add_argument("--max-relationships", type=int, default=50000)
    parser.add_argument("--max-calls", type=int, default=50000)
    parser.add_argument("--max-imports", type=int, default=10000)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--format", choices=["text", "json"], default="text")
    output.add_argument(
        "--graph", action="store_true", help="Emit canonical apizr.graph/v1 JSON only"
    )
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args(argv)
    try:
        scan_policy = ScanPolicy(
            source_roots=tuple(args.source_root or ["."]),
            excluded_directories=(
                *ScanPolicy().excluded_directories,
                *args.exclude_dir,
            ),
            max_file_bytes=args.max_file_bytes,
            max_source_files=args.max_source_files,
            max_total_bytes=args.max_total_bytes,
            max_entries=args.max_entries,
            max_depth=args.max_depth,
        )
        policy = GraphPolicy(
            max_ast_nodes=args.max_ast_nodes,
            max_relationships=args.max_relationships,
            max_calls=args.max_calls,
            max_imports=args.max_imports,
        )
        result = graph_repository(
            args.root, scan_policy=scan_policy, graph_policy=policy
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
