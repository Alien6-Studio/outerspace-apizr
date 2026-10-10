"""Explicit serving bridge CLI; shared repository authority and option validation."""

import argparse
import sys
from pathlib import Path

from apizr.cli.commands.repository import (
    add_graph_arguments,
    add_scan_arguments,
    graph_policy,
    scan_policy,
)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("run_id", metavar="RUN")
    add_scan_arguments(parser, root_option=True)
    add_graph_arguments(parser)
    parser.add_argument(
        "--store",
        type=Path,
        help="History directory; default: ROOT/.apizr/experiments/v1",
    )
    parser.add_argument(
        "--capability",
        required=True,
        action="append",
        help="Exactly one python:module:symbol ID",
    )
    parser.add_argument(
        "--interface", required=True, action="append", choices=("rest", "mcp")
    )
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="Exact recorded output name; repeat to select more",
    )
    parser.add_argument(
        "--dependency",
        action="append",
        default=[],
        help="Distribution name; version comes only from the Run",
    )
    parser.add_argument("--readiness-policy", type=Path)
    parser.add_argument("--allow-conditional", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")


def expose(args: argparse.Namespace) -> int:
    from apizr.cli.commands.repository_readiness import load_policy
    from apizr.experiments.exposure import expose_run
    from apizr.experiments.exposure_model import ExperimentExposureRefused
    from apizr.experiments.history import show_run
    from apizr.experiments.store import DEFAULT_STORE, StoreError
    from apizr.exposure import ExposureRefused
    from apizr.repository_interfaces import BundleRefused
    from apizr.repository_interfaces.output import write_bundle
    from apizr.workspace.operator_policy import (
        AuthorizationDenied,
        load_operator_policy,
    )

    try:
        if len(args.capability) != 1 or len(args.interface) != 1:
            raise ExperimentExposureRefused("experiment_selection_requires_one")
        record = show_run(args.store or args.root / DEFAULT_STORE, args.run_id)
        result = expose_run(
            record,
            args.root,
            capability=args.capability[0],
            interface=args.interface[0],
            artifacts=tuple(args.artifact),
            dependencies=tuple(args.dependency),
            allow_conditional=args.allow_conditional,
            operator_policy=load_operator_policy(args.operator_policy)
            if args.operator_policy
            else None,
            scan_policy=scan_policy(args),
            graph_policy=graph_policy(args),
            readiness_policy=load_policy(args.readiness_policy)
            if args.readiness_policy
            else None,
        )
        write_bundle(args.output_dir, result.bundle)
    except (ExperimentExposureRefused, StoreError) as error:
        print(f"apizr experiment expose: {error}", file=sys.stderr)
        return 2
    except AuthorizationDenied as error:
        print(error.decision.model_dump_json(by_alias=True), file=sys.stderr)
        return 2
    except ExposureRefused as error:
        print("apizr experiment expose: repository_exposure_refused", file=sys.stderr)
        for diagnostic in error.diagnostics:
            print(diagnostic.model_dump_json(), file=sys.stderr)
        return 1
    except BundleRefused as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, SyntaxError, UnicodeError, RecursionError):
        print("apizr experiment expose: invalid_or_inaccessible_input", file=sys.stderr)
        return 2
    if args.format == "json":
        from apizr.contracts.json import encode

        sys.stdout.buffer.write(
            encode(result.result.model_dump(mode="json"), 2 * 1024 * 1024)
        )
    else:
        binding = result.result.binding
        print(
            f"Run: {binding.run_digest}\nPlan: {binding.plan_digest}\nCapability: {binding.capability}\nInterface: {binding.interface}"
        )
        print(
            "Resources: "
            + (", ".join(output.name for output in binding.outputs) or "none")
        )
        print("Dependencies: " + (", ".join(binding.dependencies) or "none"))
        print("Bundle: " + result.result.bundle_manifest_digest.value)
    return 0
