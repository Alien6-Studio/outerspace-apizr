"""Static and runtime commands, separate from the historical generation parser."""

import argparse
import sys
from pathlib import Path
from typing import Sequence


def _inspect(argv: Sequence[str]) -> int:
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
    from apizr.inspection import inspect_file, json_bytes, text_report

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


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "scan":
        from apizr.scan_cli import main as scan_command

        return scan_command(arguments[1:])
    if arguments and arguments[0] == "execute":
        from apizr.execute_cli import main as execute_command

        return execute_command(arguments[1:])
    if arguments and arguments[0] == "inspect":
        return _inspect(arguments[1:])
    if arguments and arguments[0] == "generate":
        from apizr.generate_cli import main as generate_modern

        return generate_modern(arguments[1:])
    from apizr.main import main as generate

    if arguments in (["--help"], ["-h"]):
        try:
            generate(arguments)
        except SystemExit as exc:
            if exc.code != 0:
                raise
        print(
            "\nStatic inspection: apizr inspect SOURCE [--format json | --ir] [--module-name NAME]"
        )
        print(
            "Modern REST generation: apizr generate rest SOURCE --output-dir DIR [--select NAMES]"
        )
        print(
            "Modern MCP generation: apizr generate mcp SOURCE --output-dir DIR [--select NAMES]"
        )
        print(
            "Experimental trusted execution: apizr execute SOURCE CAPABILITY --arguments FILE --policy FILE"
        )
        print(
            "\nStatic repository inventory: apizr scan ROOT [--source-root DIR] [--format json | --catalog]"
        )
        return 0
    generate(arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
