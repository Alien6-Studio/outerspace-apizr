"""Repository-first readiness: one bounded discovery shared by Catalog and Graph."""

import argparse
import sys
from collections.abc import Sequence

from apizr.graph import graph_repository
from apizr.repository_cli import (
    add_graph_arguments,
    add_scan_arguments,
    graph_policy,
    scan_policy,
)
from apizr.repository_readiness import assess_repository
from apizr.repository_readiness_cli import (
    add_assessment_arguments,
    load_policy,
    write_report,
)


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr readiness",
        description="Assess static repository exposure evidence with one bounded discovery.",
    )
    add_scan_arguments(parser)
    add_graph_arguments(parser)
    add_assessment_arguments(parser)
    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.policy)
        artifacts = graph_repository(
            args.root, scan_policy=scan_policy(args), graph_policy=graph_policy(args)
        )
        report = assess_repository(artifacts.catalog, artifacts.graph, policy=policy)
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
