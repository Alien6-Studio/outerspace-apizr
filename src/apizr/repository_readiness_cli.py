"""Assess saved Catalog/Graph artifacts; never rediscover repository sources."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from apizr.graph.model import Graph
from apizr.repository.model import Catalog
from apizr.repository_readiness import (
    RepositoryReadinessPolicy,
    assess_repository,
    report_bytes,
)
from apizr.repository_readiness.reporting import text_report


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr repository-readiness",
        description="Evaluate static repository evidence under an explicit policy.",
    )
    parser.add_argument("catalog", type=Path, help="Canonical apizr.catalog/v1 JSON")
    parser.add_argument("graph", type=Path, help="Canonical apizr.graph/v1 JSON")
    parser.add_argument("--policy", type=Path, help="Repository readiness policy JSON")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        catalog = Catalog.model_validate_json(args.catalog.read_bytes())
        graph = Graph.model_validate_json(args.graph.read_bytes())
        policy = (
            RepositoryReadinessPolicy.model_validate_json(args.policy.read_bytes())
            if args.policy
            else RepositoryReadinessPolicy()
        )
        report = assess_repository(catalog, graph, policy=policy)
    except (OSError, ValueError, UnicodeError, RecursionError):
        print(
            "apizr repository-readiness: invalid or inaccessible artifacts/policy, or inconsistent linkage",
            file=sys.stderr,
        )
        return 2
    if args.format == "json":
        sys.stdout.buffer.write(report_bytes(report))
    else:
        print(text_report(report), end="")
    return report.exit_code
