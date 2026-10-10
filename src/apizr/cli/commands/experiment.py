"""Experiment inspection arguments and presentation; no run or history commands."""

import argparse
import sys
from pathlib import Path
from typing import Sequence

from apizr.environment.extras import MissingExtra


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr experiment",
        description="Understand experiment evidence without executing code.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser(
        "inspect", help="Inspect one Python script or notebook without executing it"
    )
    inspect.add_argument("source", type=Path)
    inspect.add_argument("--format", choices=("text", "json"), default="text")
    inspect.add_argument(
        "--module-name",
        help="Logical dotted module identity; defaults to the filename stem",
    )
    inspect.add_argument(
        "--root",
        type=Path,
        help="Root for portable source/input references and environment specs; defaults to source parent",
    )
    inspect.add_argument(
        "--max-input-bytes",
        type=int,
        default=1024**3,
        help="Maximum bytes per local input (default: 1 GiB; maximum: 1 TiB)",
    )
    inspect.add_argument(
        "--input",
        action="append",
        default=[],
        metavar="NAME=REFERENCE",
        help="Explicit input declaration; does not resolve dynamic Python expressions",
    )
    args = parser.parse_args(argv)
    from apizr.experiments.inputs import FingerprintPolicy, parse_input_declaration
    from apizr.experiments.inspection import inspect_experiment
    from apizr.experiments.reporting import inspection_bytes, text_report

    try:
        result = inspect_experiment(
            args.source,
            root=args.root,
            module_name=args.module_name,
            declarations=tuple(parse_input_declaration(value) for value in args.input),
            fingerprint_policy=FingerprintPolicy(max_file_bytes=args.max_input_bytes),
        )
        output = (
            inspection_bytes(result)
            if args.format == "json"
            else text_report(result).encode("utf-8")
        )
    except MissingExtra:
        raise
    except (OSError, ValueError, SyntaxError, UnicodeError, RecursionError):
        # Exceptions can contain arbitrary source fragments, paths or notebook output.
        print(
            "apizr experiment inspect: unable to inspect source; check Python syntax, source/root, input declarations, size limits and notebook support.",
            file=sys.stderr,
        )
        return 2
    sys.stdout.buffer.write(output)
    return 0
