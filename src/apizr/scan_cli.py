"""Offline repository scan command; existing commands remain separate."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from apizr.repository import ScanPolicy, catalog_bytes, scan
from apizr.repository.reporting import envelope_bytes, text_report


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr scan",
        description="Statically inventory Python sources without imports, Git or network access.",
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
        help="Additional exact directory basename to exclude",
    )
    parser.add_argument("--max-file-bytes", type=int, default=1048576)
    parser.add_argument("--max-source-files", type=int, default=1000)
    parser.add_argument("--max-total-bytes", type=int, default=16777216)
    parser.add_argument("--max-entries", type=int, default=20000)
    parser.add_argument("--max-depth", type=int, default=64)
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
        policy = ScanPolicy(
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
        catalog = scan(args.root, policy=policy)
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
