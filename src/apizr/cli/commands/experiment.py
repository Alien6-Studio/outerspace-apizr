"""Experiment lifecycle arguments, lazy dispatch and sanitized presentation."""

import argparse
import sys
from pathlib import Path
from typing import Sequence

from apizr.environment.extras import MissingExtra

TRUST_WARNING = (
    "Executes trusted user code in a fresh process with host filesystem, network "
    "and subprocess access. This is not a security sandbox."
)


def _source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--module-name",
        help="Logical dotted module identity; defaults to the filename stem",
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="Root for portable source/input references and environment specs; defaults to source parent",
    )
    parser.add_argument(
        "--max-input-bytes",
        type=int,
        default=1024**3,
        help="Maximum bytes per local input (default: 1 GiB; maximum: 1 TiB)",
    )
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        metavar="NAME=REFERENCE",
        help="Explicit input declaration; does not resolve dynamic Python expressions",
    )


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr experiment",
        description="Inspect → Run → Compare → Expose: explicit evidence and serving choices.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser(
        "inspect", help="Inspect one Python script or notebook without executing it"
    )
    _source_arguments(inspect)
    run = commands.add_parser(
        "run",
        help="Execute trusted code and persist observed evidence",
        description=TRUST_WARNING,
    )
    _source_arguments(run)
    run.add_argument(
        "--store",
        type=Path,
        help="History directory; default: ROOT/.apizr/experiments/v1",
    )
    run.add_argument(
        "--timeout-ms",
        type=int,
        default=60_000,
        help="Wall timeout in ms (default: 60000; maximum: 3600000)",
    )
    environment = run.add_mutually_exclusive_group()
    environment.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME",
        help="Inherit only named environment variables; default environment is clean",
    )
    environment.add_argument(
        "--inherit-environment",
        action="store_true",
        help="Explicitly inherit the complete parent environment",
    )
    run.add_argument(
        "--metric",
        action="append",
        default=[],
        metavar="NAME=IDENTIFIER",
        help="Require a finite metric from a final global binding (no expressions)",
    )
    run.add_argument(
        "--output",
        action="append",
        default=[],
        metavar="NAME=REFERENCE",
        help="Require a root-relative output fingerprint after successful execution",
    )
    run.add_argument(
        "--max-output-bytes",
        type=int,
        default=1024**3,
        help="Maximum bytes per output (default: 1 GiB; maximum: 1 TiB)",
    )
    listing = commands.add_parser("list", help="List validated local Runs")
    listing.add_argument("--status", choices=("success", "failed", "cancelled"))
    listing.add_argument("--source", help="Exact portable source reference")
    listing.add_argument(
        "--capability", help="Exact capability ID; whole workloads normally have none"
    )
    listing.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum displayed Runs (default: 20; maximum: 1000)",
    )
    show = commands.add_parser(
        "show", help="Show intended Plan and observed Run evidence"
    )
    show.add_argument(
        "run_id",
        metavar="RUN",
        help="Full Run SHA-256 or unique lowercase prefix of at least 12 characters",
    )
    diff = commands.add_parser(
        "diff", help="Compare recorded evidence, A to B; no causal inference"
    )
    for name in ("run_a", "run_b"):
        diff.add_argument(
            name,
            metavar=name.upper(),
            help="Full Run SHA-256 or unique lowercase prefix of at least 12 characters",
        )
    for history in (listing, show, diff):
        history.add_argument(
            "--store",
            type=Path,
            help="History directory; default: .apizr/experiments/v1 under current directory",
        )
        history.add_argument("--format", choices=("text", "json"), default="text")
    from apizr.cli.commands.experiment_exposure import add_arguments

    exposure = commands.add_parser(
        "expose",
        help="Bridge a reviewed successful Run to an explicit REST/MCP capability",
    )
    add_arguments(exposure)
    args = parser.parse_args(argv)
    if args.command == "expose":
        from apizr.cli.commands.experiment_exposure import expose

        return expose(args)
    if args.command == "inspect":
        return _inspect(args)
    if args.command == "run":
        return _run(args)
    if args.command == "diff":
        return _diff(args)
    return _history(args)


def _inspect(args: argparse.Namespace) -> int:
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
        print(
            "apizr experiment inspect: unable to inspect source; check Python syntax, source/root, input declarations, size limits and notebook support.",
            file=sys.stderr,
        )
        return 2
    sys.stdout.buffer.write(output)
    return 0


def _error(command: str, error: Exception) -> int:
    # Only reviewed stable diagnostics may reach the terminal. Validation errors
    # can include arbitrary user values, source fragments and exception text.
    code = str(error)
    if code not in {
        "source_changed",
        "input_changed",
        "plan_mismatch",
        "runner_requires_posix",
        "output_selection_limit",
        "store_corrupt",
        "store_limit",
        "store_publish_failed",
        "run_id_invalid",
        "run_id_ambiguous",
        "run_not_found",
        "metric_binding_invalid",
        "environment_modes_conflict",
    }:
        code = "invalid_request"
    print(f"apizr experiment {command}: {code}", file=sys.stderr)
    return 2


def _run(args: argparse.Namespace) -> int:
    from apizr.experiments.history import history_bytes, summary, summary_text
    from apizr.experiments.inputs import FingerprintPolicy, parse_input_declaration
    from apizr.experiments.outputs import parse_output_declaration
    from apizr.experiments.planning import RunOptions, parse_metric_binding
    from apizr.experiments.runner import run_experiment

    print(TRUST_WARNING, file=sys.stderr)
    try:
        result = run_experiment(
            args.source,
            root=args.root,
            module_name=args.module_name,
            store=args.store,
            declarations=tuple(parse_input_declaration(value) for value in args.input),
            fingerprint_policy=FingerprintPolicy(max_file_bytes=args.max_input_bytes),
            options=RunOptions(
                timeout_ms=args.timeout_ms,
                inherit_environment=args.inherit_environment,
                environment_names=tuple(args.env),
                metrics=tuple(parse_metric_binding(value) for value in args.metric),
                outputs=tuple(parse_output_declaration(value) for value in args.output),
                max_output_bytes=args.max_output_bytes,
            ),
        )
        brief = summary(result)
        output = (
            history_bytes(brief)
            if args.format == "json"
            else summary_text(brief).encode("utf-8")
        )
    except MissingExtra:
        raise
    except (OSError, ValueError, SyntaxError, UnicodeError, RecursionError) as error:
        return _error("run", error)
    sys.stdout.buffer.write(output)
    return 0 if result.run.status == "success" else 1


def _diff(args: argparse.Namespace) -> int:
    from apizr.experiments.comparison import compare_runs, diff_bytes
    from apizr.experiments.comparison_reporting import diff_text
    from apizr.experiments.history import show_run
    from apizr.experiments.store import DEFAULT_STORE

    try:
        path = args.store if args.store is not None else DEFAULT_STORE
        result = compare_runs(show_run(path, args.run_a), show_run(path, args.run_b))
        output = (
            diff_bytes(result)
            if args.format == "json"
            else diff_text(result).encode("utf-8")
        )
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        return _error("diff", error)
    sys.stdout.buffer.write(output)
    return 0


def _history(args: argparse.Namespace) -> int:
    from apizr.experiments.history import (
        HistoryQuery,
        history_bytes,
        list_runs,
        list_text,
        show_run,
        show_text,
    )
    from apizr.experiments.store import DEFAULT_STORE

    try:
        path = args.store if args.store is not None else DEFAULT_STORE
        if args.command == "list":
            listing = list_runs(
                path,
                query=HistoryQuery(
                    status=args.status,
                    source=args.source,
                    capability=args.capability,
                    limit=args.limit,
                ),
            )
            output = (
                history_bytes(listing)
                if args.format == "json"
                else list_text(listing).encode("utf-8")
            )
        else:
            record = show_run(path, args.run_id)
            output = (
                history_bytes(record)
                if args.format == "json"
                else show_text(record).encode("utf-8")
            )
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        return _error(args.command, error)
    sys.stdout.buffer.write(output)
    return 0
