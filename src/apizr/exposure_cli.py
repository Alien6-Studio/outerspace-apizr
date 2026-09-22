"""One bounded repository discovery followed by pure exposure planning."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from apizr.exposure import (
    ExposurePolicy,
    ExposureRefused,
    plan_bytes,
    plan_exposure,
    refusal_report,
    text_report,
)
from apizr.graph import graph_repository
from apizr.repository_cli import (
    add_graph_arguments,
    add_scan_arguments,
    graph_policy,
    scan_policy,
)
from apizr.repository_readiness import assess_repository
from apizr.repository_readiness_cli import load_policy


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr expose", description="Explicit repository exposure planning."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser(
        "plan", help="Plan explicit exposure over static evidence"
    )
    add_scan_arguments(command)
    add_graph_arguments(command)
    command.add_argument(
        "--policy",
        type=Path,
        help="Exposure policy JSON; cannot be mixed with inline exposure choices",
    )
    command.add_argument(
        "--readiness-policy",
        type=Path,
        help="Independent repository readiness policy JSON",
    )
    command.add_argument("--interface", action="append", choices=("rest", "mcp"))
    command.add_argument(
        "--execution-mode",
        action="append",
        choices=("direct", "local-process", "oci-container"),
    )
    command.add_argument("--require-control", action="append")
    command.add_argument(
        "--select",
        action="append",
        help="Exact python:module:symbol ID; repeat to select more",
    )
    command.add_argument(
        "--exclude", action="append", help="Exact capability ID; exclusion always wins"
    )
    command.add_argument("--all-ready", action="store_true")
    command.add_argument("--allow-conditional", action="store_true")
    command.add_argument(
        "--plan", action="store_true", help="Emit only canonical Exposure Plan JSON"
    )
    args = parser.parse_args(argv)
    policy: ExposurePolicy | None = None
    try:
        if args.policy:
            if any(
                (
                    args.interface,
                    args.execution_mode,
                    args.require_control,
                    args.select,
                    args.exclude,
                    args.all_ready,
                    args.allow_conditional,
                )
            ):
                raise ValueError("Policy and inline choices cannot be mixed")
            policy = ExposurePolicy.model_validate_json(args.policy.read_bytes())
        else:
            policy = ExposurePolicy.model_validate(
                {
                    "selection": {
                        "include": args.select or [],
                        "exclude": args.exclude or [],
                        "include_all_ready": args.all_ready,
                    },
                    "interfaces": args.interface or [],
                    "execution": {
                        "allowed": args.execution_mode or [],
                        "require": args.require_control or [],
                    },
                    "eligibility": {"allow_conditional": args.allow_conditional},
                }
            )
        readiness_policy = load_policy(args.readiness_policy)
        artifacts = graph_repository(
            args.root, scan_policy=scan_policy(args), graph_policy=graph_policy(args)
        )
        readiness = assess_repository(
            artifacts.catalog, artifacts.graph, policy=readiness_policy
        )
        plan = plan_exposure(
            artifacts.catalog, artifacts.graph, readiness, policy=policy
        )
    except ExposureRefused as error:
        assert policy is not None
        print(refusal_report(error, policy), end="", file=sys.stderr)
        return 1
    except (OSError, ValueError, UnicodeError, RecursionError):
        print(
            "apizr expose plan: invalid/inaccessible policy or repository input; declare interfaces and execution modes, check roots and bounds",
            file=sys.stderr,
        )
        return 2
    if args.plan:
        sys.stdout.buffer.write(plan_bytes(plan))
    else:
        print(text_report(plan, readiness), end="")
    return 0
