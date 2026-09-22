"""One bounded repository discovery followed by pure exposure planning."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from apizr.execution.policy import ExecutionPolicy, PolicyRefused
from apizr.exposure import (
    ExposurePolicy,
    ExposureRefused,
    plan_bytes,
    plan_exposure,
    refusal_report,
    text_report,
)
from apizr.graph import analyze_repository
from apizr.oci.model import ExecutionPolicyV2, RuntimeImage
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
        description="Explicit repository exposure planning and REST/MCP bundles.",
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
        "build", help="Build a direct or governed repository REST or MCP bundle"
    )
    build.add_argument("target_interface", choices=("rest", "mcp"))
    add_policy_arguments(build)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--execution-policy", type=Path)
    build.add_argument("--runtime-image")
    build.add_argument("--runtime-platform", choices=("linux/amd64", "linux/arm64"))
    args = parser.parse_args(argv)
    execution_policy: ExecutionPolicy | ExecutionPolicyV2 | None = None
    runtime_image: RuntimeImage | None = None
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

            if args.execution_policy is not None:
                with args.execution_policy.open("rb") as stream:
                    raw_policy = stream.read(1048577)
                if len(raw_policy) > 1048576:
                    raise ValueError("Execution policy exceeds size limit")
                document = json.loads(raw_policy)
                if (
                    isinstance(document, dict)
                    and cast(dict[str, object], document).get("schema_version")
                    == "apizr.execution/v2"
                ):
                    execution_policy = ExecutionPolicyV2.model_validate_json(raw_policy)
                    if not args.runtime_image or not args.runtime_platform:
                        raise ValueError("OCI requires image and platform")
                    runtime_image = RuntimeImage(
                        image=args.runtime_image, platform=args.runtime_platform
                    )
                else:
                    execution_policy = ExecutionPolicy.model_validate_json(raw_policy)
            if runtime_image is None and (args.runtime_image or args.runtime_platform):
                raise ValueError("Runtime image requires OCI policy")
            bundle = render_repository_bundle(
                artifacts.catalog,
                artifacts.graph,
                readiness,
                policy,
                plan,
                artifacts.sources,
                interface=args.target_interface,
                execution_policy=execution_policy,
                runtime_image=runtime_image,
            )
            write_bundle(args.output_dir, bundle)
    except PolicyRefused as error:
        print(
            f"apizr expose build: execution policy refused ({error})", file=sys.stderr
        )
        return 1
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
        if execution_policy is not None:
            print(
                f"Execution: governed\nConfigured backend: {execution_policy.backend}\nCapabilities: {len(plan.capabilities)}"
            )
            if runtime_image is not None:
                print("Provider: docker-engine")
    elif args.plan:
        sys.stdout.buffer.write(plan_bytes(plan))
    else:
        print(text_report(plan, readiness), end="")
    return 0
