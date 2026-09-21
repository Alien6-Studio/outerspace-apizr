"""Assess saved Catalog/Graph artifacts; never rediscover repository sources."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from apizr.graph.model import Graph
from apizr.repository.model import Catalog
from apizr.repository_readiness import (
    RepositoryReadinessPolicy,
    RepositoryReadinessReport,
    assess_repository,
    report_bytes,
)
from apizr.repository_readiness.reporting import text_report


def add_assessment_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--policy", type=Path, help="Repository readiness policy JSON")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--format", choices=("text", "json"), default="text")
    output.add_argument(
        "--report",
        action="store_true",
        help="Emit only canonical apizr.repository-readiness/v1 JSON",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Expand declaration evidence in human output",
    )


def load_policy(path: Path | None) -> RepositoryReadinessPolicy:
    return (
        RepositoryReadinessPolicy.model_validate_json(path.read_bytes())
        if path
        else RepositoryReadinessPolicy()
    )


def write_report(
    report: RepositoryReadinessReport, *, canonical: bool, details: bool = True
) -> None:
    if canonical:
        sys.stdout.buffer.write(report_bytes(report))
    else:
        print(text_report(report, details=details), end="")


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr repository-readiness",
        description="Evaluate static repository evidence under an explicit policy.",
    )
    parser.add_argument("catalog", type=Path, help="Canonical apizr.catalog/v1 JSON")
    parser.add_argument("graph", type=Path, help="Canonical apizr.graph/v1 JSON")
    add_assessment_arguments(parser)
    args = parser.parse_args(argv)
    try:
        catalog = Catalog.model_validate_json(args.catalog.read_bytes())
        graph = Graph.model_validate_json(args.graph.read_bytes())
        policy = load_policy(args.policy)
        report = assess_repository(catalog, graph, policy=policy)
    except (OSError, ValueError, UnicodeError, RecursionError):
        print(
            "apizr repository-readiness: invalid or inaccessible artifacts/policy, or inconsistent linkage",
            file=sys.stderr,
        )
        return 2
    # Preserve artifact-first's existing complete text report by default.
    write_report(report, canonical=args.report or args.format == "json")
    return report.exit_code
