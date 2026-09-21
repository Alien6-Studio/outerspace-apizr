"""Shared bounded repository options for Scan, Graph and Readiness commands."""

import argparse
from pathlib import Path

from apizr.graph.policy import GraphPolicy
from apizr.repository.policy import ScanPolicy


def add_scan_arguments(parser: argparse.ArgumentParser) -> None:
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
        help="Additional exact directory basename to exclude",
    )
    defaults = ScanPolicy()
    parser.add_argument("--max-file-bytes", type=int, default=defaults.max_file_bytes)
    parser.add_argument(
        "--max-source-files", type=int, default=defaults.max_source_files
    )
    parser.add_argument("--max-total-bytes", type=int, default=defaults.max_total_bytes)
    parser.add_argument("--max-entries", type=int, default=defaults.max_entries)
    parser.add_argument("--max-depth", type=int, default=defaults.max_depth)


def add_graph_arguments(parser: argparse.ArgumentParser) -> None:
    defaults = GraphPolicy()
    parser.add_argument("--max-ast-nodes", type=int, default=defaults.max_ast_nodes)
    parser.add_argument(
        "--max-relationships", type=int, default=defaults.max_relationships
    )
    parser.add_argument("--max-calls", type=int, default=defaults.max_calls)
    parser.add_argument("--max-imports", type=int, default=defaults.max_imports)


def scan_policy(args: argparse.Namespace) -> ScanPolicy:
    return ScanPolicy(
        source_roots=tuple(args.source_root or ["."]),
        excluded_directories=(*ScanPolicy().excluded_directories, *args.exclude_dir),
        max_file_bytes=args.max_file_bytes,
        max_source_files=args.max_source_files,
        max_total_bytes=args.max_total_bytes,
        max_entries=args.max_entries,
        max_depth=args.max_depth,
    )


def graph_policy(args: argparse.Namespace) -> GraphPolicy:
    return GraphPolicy(
        max_ast_nodes=args.max_ast_nodes,
        max_relationships=args.max_relationships,
        max_calls=args.max_calls,
        max_imports=args.max_imports,
    )
