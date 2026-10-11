"""Repository-first readiness: one bounded discovery shared by Catalog and Graph."""

import argparse
import sys
from collections.abc import Sequence

from apizr.cli.commands.git_source import add_git_arguments, apply_input, input_root
from apizr.cli.commands.repository import (
    add_graph_arguments,
    add_scan_arguments,
    graph_policy,
    scan_policy,
)
from apizr.cli.commands.repository_readiness import (
    add_assessment_arguments,
    load_policy,
    write_report,
)
from apizr.git_source import GitSourceError
from apizr.workspace.compiler import assess_readiness
from apizr.workspace.operator_policy import AuthorizationDenied


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr readiness",
        description="Assess static repository exposure evidence with one bounded discovery.",
    )
    add_scan_arguments(parser, project=True)
    add_graph_arguments(parser, project=True)
    add_git_arguments(parser)
    add_assessment_arguments(parser)
    args = parser.parse_args(argv)
    try:
        apply_input(parser, args)
        policy = load_policy(args.policy)
        with input_root(args) as (root, authority):
            report = assess_readiness(
                root,
                operator_policy=authority,
                scan_policy=scan_policy(args),
                graph_policy=graph_policy(args),
                readiness_policy=policy,
            )
    except KeyboardInterrupt:
        if args.git is None:
            raise
        print("apizr readiness: git_cancelled", file=sys.stderr)
        return 130
    except AuthorizationDenied as error:
        print(error.decision.model_dump_json(by_alias=True), file=sys.stderr)
        return 2
    except GitSourceError as error:
        print(f"apizr readiness: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, UnicodeError, RecursionError):
        print(
            "apizr readiness: invalid policy/input or inaccessible repository root; check roots and bounds",
            file=sys.stderr,
        )
        return 2
    write_report(
        report, canonical=args.report or args.format == "json", details=args.details
    )
    return report.exit_code
