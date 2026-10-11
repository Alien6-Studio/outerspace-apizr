"""Explicit preparation arguments and typed outcome presentation."""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from apizr.plugins.preparation.models import (
    MAX_REQUIREMENTS_BYTES,
    Diagnostic,
    PreparationError,
)
from apizr.plugins.preparation.operations import prepare_plugin
from apizr.plugins.preparation.requirements import parse_resolver_lock
from apizr.workspace.files import read_regular


def add_arguments(
    parser: argparse.ArgumentParser, timeout: Callable[[str], int]
) -> None:
    parser.add_argument("name", help="Exact plugin distribution name")
    parser.add_argument("--version", required=True, help="Exact plugin version")
    parser.add_argument(
        "--python",
        type=Path,
        required=True,
        help="Absolute path to the plugin environment interpreter",
    )
    parser.add_argument(
        "--platform",
        required=True,
        help="native or the measured native platform; cross-platform builds are refused",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="New prepared directory, including an empty isolated profile",
    )
    parser.add_argument(
        "--wheelhouse",
        type=Path,
        help="Explicit local candidate wheels; remains offline without --index-url",
    )
    parser.add_argument(
        "--index-url",
        help="Explicit HTTPS package index; authorizes preparation network access",
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        help="Optional resolver lock with admitted SHA-256 hash sets",
    )
    parser.add_argument(
        "--uv",
        type=Path,
        help="Explicit uv 0.12 executable; otherwise use the recorded executable on PATH",
    )
    parser.add_argument("--timeout-ms", type=timeout, default=120000)
    parser.add_argument(
        "--json", action="store_true", help="Emit the versioned preparation result"
    )


def run(args: argparse.Namespace) -> int:
    result = prepare_plugin(
        args.name,
        args.version,
        python=args.python,
        platform=args.platform,
        output_dir=args.output_dir,
        wheelhouse=args.wheelhouse,
        requirements=args.requirements,
        index_url=args.index_url,
        uv=args.uv,
        timeout_ms=args.timeout_ms,
    )
    if args.json:
        print(result.model_dump_json(by_alias=True))
    elif result.state == "prepared":
        print(f"Prepared {args.name} {args.version} in {args.output_dir}")
        print(
            "Install the retained wheels, then explicitly enable the plugin in the prepared profile."
        )
    for problem in result.diagnostics:
        if problem.reason == "preparation_extra_required":
            print(
                "Install Apizr with its [preparation] extra to enable wheel selection.",
                file=sys.stderr,
            )
        distribution = f" ({problem.distribution})" if problem.distribution else ""
        print(f"apizr plugins prepare: {problem.reason}{distribution}", file=sys.stderr)
    return result.exit_code


def explain_installer_lock(path: Path | None) -> None:
    if path is None:
        return
    try:
        pins = parse_resolver_lock(read_regular(path, MAX_REQUIREMENTS_BYTES))
        affected = next((pin for pin in pins if len(pin.hashes) > 1), None)
        if affected is not None:
            print(
                Diagnostic(
                    reason="multiple_hashes_require_preparation",
                    distribution=affected.name,
                    version=affected.version,
                ).model_dump_json(),
                file=sys.stderr,
            )
    except (OSError, ValueError, PreparationError):
        return
