"""Static and runtime commands, separate from the historical generation parser."""

import argparse
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Sequence

from apizr.optional import MissingExtra, available, require


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
    try:
        return _main(argv)
    except MissingExtra as error:
        print(f"apizr: {error}", file=sys.stderr)
        return 2


def _main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--version"]:
        print(f"outerspace-apizr {version('outerspace-apizr')}")
        return 0
    if arguments and arguments[0] == "mcp":
        from apizr.mcp_cli import main as mcp_command

        return mcp_command(arguments[1:])
    if arguments and arguments[0] == "plugins":
        from apizr.plugins_cli import main as plugins_command

        return plugins_command(arguments[1:])
    if arguments and arguments[0] == "expose":
        from apizr.exposure_cli import main as exposure_command

        return exposure_command(arguments[1:])
    if arguments and arguments[0] == "readiness":
        from apizr.readiness_cli import main as readiness_repo_command

        return readiness_repo_command(arguments[1:])
    if arguments and arguments[0] == "repository-readiness":
        from apizr.repository_readiness_cli import main as readiness_command

        return readiness_command(arguments[1:])
    if arguments and arguments[0] == "graph":
        from apizr.graph_cli import main as graph_command

        return graph_command(arguments[1:])
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
    if arguments in (["--help"], ["-h"]):
        print("Apizr — an open-source capability compiler for Python codebases.\n")
        print("Version: apizr --version")
        print("Local MCP analysis server (optional plugin): apizr mcp serve --help")
        print("Extensions: apizr plugins {install,list,enable,disable,run} --help")
        print(
            "\nRepository workflow: Discover → Understand → Assess → Select → Expose → Execute"
        )
        print("Discover: apizr scan ROOT [--source-root DIR] [--catalog]")
        print("Understand: apizr graph ROOT [--source-root DIR] [--graph]")
        print("Assess: apizr readiness ROOT [--policy READINESS.json] [--report]")
        print("Select: apizr expose plan ROOT --policy EXPOSURE.json [--plan]")
        print(
            "Expose: apizr expose build {rest,mcp} ROOT --policy EXPOSURE.json --output-dir DIR"
        )
        print(
            "  Add --execution-policy EXECUTION.json for fresh local/OCI workers; default: direct."
        )
        print(
            "  READY does not mean exposed. Supporting dependencies are not automatically public."
        )
        print("\nSingle-source workflows (Python or notebook):")
        print("  apizr inspect SOURCE [--format json | --ir] [--module-name NAME]")
        print("  apizr generate {rest,mcp} SOURCE --output-dir DIR [--select NAMES]")
        print("  apizr execute SOURCE CAPABILITY --arguments FILE --policy FILE")
        print(
            "  Execution is trusted-code oriented; local processes are not filesystem/network sandboxes."
        )
        print(
            "Artifact-first readiness: apizr repository-readiness CATALOG GRAPH --policy FILE"
        )
        print("\nLegacy generation pipeline (retained for compatibility):")
        if not available(
            "yaml", "questionary", "jinja2", "packaging", "nbconvert", "black"
        ):
            print("  apizr --script FILE | --notebook FILE --output-dir DIR")
            print(
                "  Install outerspace-apizr[legacy] for legacy generation and its full help."
            )
            return 0
        from apizr.main import main as generate

        try:
            generate(arguments)
        except SystemExit as exc:
            if exc.code != 0:
                raise
        return 0
    require(
        "legacy", "yaml", "questionary", "jinja2", "packaging", "nbconvert", "black"
    )
    from apizr.main import main as generate

    generate(arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
