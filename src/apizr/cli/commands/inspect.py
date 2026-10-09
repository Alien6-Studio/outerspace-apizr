"""Inspect command: parse arguments and present static source evidence."""

import argparse
import sys
from pathlib import Path
from typing import Sequence


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr inspect",
        description="Inspect one Python source or notebook without executing it.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--module-name",
        help="Logical dotted module identity; defaults to the filename stem",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--format", choices=("text", "json"), default="text")
    output.add_argument(
        "--ir",
        action="store_true",
        help="Emit only canonical Capability IR bytes (same inspection exit policy)",
    )
    args = parser.parse_args(argv)
    from apizr.capabilities import canonical_bytes
    from apizr.capabilities.inspection import inspect_file, json_bytes, text_report

    try:
        inspection = inspect_file(
            args.source, module_name=args.module_name or args.source.stem
        )
    except (OSError, ValueError, SyntaxError, UnicodeError, RecursionError) as exc:
        # SyntaxError's repr can contain input fragments; only expose its parser message.
        message = exc.msg if isinstance(exc, SyntaxError) else str(exc)
        print(f"apizr inspect: {message}", file=sys.stderr)
        return 2
    if args.ir:
        sys.stdout.buffer.write(canonical_bytes(inspection.capability_ir))
    elif args.format == "json":
        sys.stdout.buffer.write(json_bytes(inspection))
    else:
        print(text_report(inspection), end="")
    return inspection.exit_code
