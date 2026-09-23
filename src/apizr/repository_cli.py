"""Shared bounded repository options for Scan, Graph and Readiness commands."""

import argparse
from pathlib import Path

from apizr.graph.policy import GraphPolicy
from apizr.repository.policy import ScanPolicy


def add_scan_arguments(
    parser: argparse.ArgumentParser, *, project: bool = False
) -> None:
    if project:
        parser.add_argument("root", type=Path, nargs="?")
        parser.add_argument(
            "--project", type=Path, help="Explicit apizr.toml project file"
        )
    else:
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
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=argparse.SUPPRESS if project else defaults.max_file_bytes,
    )
    parser.add_argument(
        "--max-source-files",
        type=int,
        default=argparse.SUPPRESS if project else defaults.max_source_files,
    )
    parser.add_argument(
        "--max-total-bytes",
        type=int,
        default=argparse.SUPPRESS if project else defaults.max_total_bytes,
    )
    parser.add_argument(
        "--max-entries",
        type=int,
        default=argparse.SUPPRESS if project else defaults.max_entries,
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=argparse.SUPPRESS if project else defaults.max_depth,
    )


def add_graph_arguments(
    parser: argparse.ArgumentParser, *, project: bool = False
) -> None:
    defaults = GraphPolicy()
    parser.add_argument(
        "--max-ast-nodes",
        type=int,
        default=argparse.SUPPRESS if project else defaults.max_ast_nodes,
    )
    parser.add_argument(
        "--max-relationships",
        type=int,
        default=argparse.SUPPRESS if project else defaults.max_relationships,
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        default=argparse.SUPPRESS if project else defaults.max_calls,
    )
    parser.add_argument(
        "--max-imports",
        type=int,
        default=argparse.SUPPRESS if project else defaults.max_imports,
    )


def apply_project(
    parser: argparse.ArgumentParser, args: argparse.Namespace, *, exposure: bool = False
) -> None:
    """Fill only absent CLI options; preserve additive directory exclusions.

    Policy files are selected whole, never merged. The exposure parser retains
    its existing rejection of policy files combined with inline choices.
    """
    if args.root is None and args.project is None:
        parser.error("the following arguments are required: root")
    from apizr.project import load_project

    config = load_project(args.project) if args.project is not None else None
    scan = config.scan if config is not None else ScanPolicy()
    graph = config.graph if config is not None else GraphPolicy()
    for name in (
        "max_file_bytes",
        "max_source_files",
        "max_total_bytes",
        "max_entries",
        "max_depth",
    ):
        if not hasattr(args, name):
            setattr(args, name, getattr(scan, name))
    for name in ("max_ast_nodes", "max_relationships", "max_calls", "max_imports"):
        if not hasattr(args, name):
            setattr(args, name, getattr(graph, name))
    if config is not None:
        if args.root is None:
            args.root = config.root
        if args.source_root is None:
            args.source_root = list(config.scan.source_roots)
        args.exclude_dir = [*config.scan.excluded_directories, *args.exclude_dir]
        if args.policy is None:
            args.policy = (
                config.exposure_policy if exposure else config.readiness_policy
            )
        if exposure and args.readiness_policy is None:
            args.readiness_policy = config.readiness_policy


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
