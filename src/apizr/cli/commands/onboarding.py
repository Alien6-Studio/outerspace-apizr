"""Local onboarding commands, sharing their typed Python API outcomes."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from apizr.interfaces.serialization import json_bytes
from apizr.onboarding import InitError, doctor, initialize_project
from apizr.onboarding.diagnostics import PROFILES


def init(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="apizr init")
    parser.add_argument("directory", type=Path, nargs="?", default=Path("."))
    parser.add_argument("--source-root", action="append")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = initialize_project(
            args.directory, source_roots=tuple(args.source_root or ["."])
        )
        if args.json:
            sys.stdout.buffer.write(json_bytes(result.model_dump(mode="json")))
        else:
            print("Created apizr.toml and .apizr policies. No capabilities selected.")
            print("From the initialized directory, run:")
            print(
                "  apizr doctor --project apizr.toml --operator-policy .apizr/operator.json"
            )
            print(
                "  apizr readiness --project apizr.toml --operator-policy .apizr/operator.json"
            )
        return 0
    except InitError as error:
        print(str(error), file=sys.stderr)
        return 130 if str(error) == "init_cancelled" else 2


def diagnose(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="apizr doctor")
    parser.add_argument("--project", type=Path, default=Path("apizr.toml"))
    parser.add_argument("--operator-policy", type=Path)
    parser.add_argument("--profile", action="append", choices=PROFILES)
    parser.add_argument("--plugins-dir", type=Path)
    parser.add_argument("--delivery-request", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = doctor(
            project=args.project,
            operator_policy=args.operator_policy,
            profiles=tuple(args.profile or ["core"]),
            plugins_dir=args.plugins_dir,
            delivery_request=args.delivery_request,
            bundle=args.bundle,
        )
        if args.json:
            sys.stdout.buffer.write(json_bytes(result.model_dump(mode="json")))
        else:
            for check in result.checks:
                print(f"{check.status.upper():4}  {check.code:26} {check.summary}")
                if check.action:
                    print(f"      {check.action}")
        return result.exit_code
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError, RecursionError):
        print("doctor_arguments_invalid", file=sys.stderr)
        return 2
