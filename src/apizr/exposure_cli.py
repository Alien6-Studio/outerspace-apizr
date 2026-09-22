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
from apizr.graph import analyze_repository
from apizr.repository_cli import (
    add_graph_arguments,
    add_scan_arguments,
    graph_policy,
    scan_policy,
)
from apizr.repository_interfaces import BundleRefused
from apizr.repository_readiness import assess_repository
from apizr.repository_readiness_cli import load_policy


def add_policy_arguments(command: argparse.ArgumentParser) -> None:
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


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr expose",
        description="Explicit repository exposure planning and direct bundles.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser(
        "plan", help="Plan explicit exposure over static evidence"
    )
    add_policy_arguments(command)
    command.add_argument(
        "--plan", action="store_true", help="Emit only canonical Exposure Plan JSON"
    )
    build = commands.add_parser(
        "build", help="Build a direct repository REST or MCP bundle"
    )
    build.add_argument("target_interface", choices=("rest", "mcp"))
    add_policy_arguments(build)
    build.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    bundle: dict[str, bytes] = {}
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
        artifacts = analyze_repository(
            args.root, scan_policy=scan_policy(args), graph_policy=graph_policy(args)
        )
        readiness = assess_repository(
            artifacts.catalog, artifacts.graph, policy=readiness_policy
        )
        plan = plan_exposure(
            artifacts.catalog, artifacts.graph, readiness, policy=policy
        )
        if args.command == "build":
            from apizr.repository_interfaces.generator import render_repository_bundle
            from apizr.repository_interfaces.output import write_bundle

            bundle = render_repository_bundle(
                artifacts.catalog,
                artifacts.graph,
                readiness,
                policy,
                plan,
                artifacts.sources,
                interface=args.target_interface,
            )
            write_bundle(args.output_dir, bundle)
    except BundleRefused as error:
        print(str(error), file=sys.stderr)
        return 1
    except ExposureRefused as error:
        assert policy is not None
        print(refusal_report(error, policy), end="", file=sys.stderr)
        return 1
    except (OSError, ValueError, UnicodeError, RecursionError):
        print(
            f"apizr expose {args.command}: invalid/inaccessible policy or repository input; declare interfaces and execution modes, check roots and bounds",
            file=sys.stderr,
        )
        return 2
    if args.command == "build":
        print(
            f"Repository {args.target_interface} bundle generated ({len(bundle)} artifacts)"
        )
    elif args.plan:
        sys.stdout.buffer.write(plan_bytes(plan))
    else:
        print(text_report(plan, readiness), end="")
    return 0
