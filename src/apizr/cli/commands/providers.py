"""Explicit provider inventory; selected external descriptors execute trusted code."""

import argparse
import sys
from pathlib import Path
from typing import Sequence


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr providers",
        description="Inspect the explicit scientific provider selection; external describe operations invoke installed trusted extensions.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser(
        "list",
        help="List configured providers, exact versions, selected capabilities and limits",
    )
    listing.add_argument(
        "--selection",
        type=Path,
        help="Explicit apizr.provider-selection/v1 JSON; default is the built-in provider only",
    )
    listing.add_argument(
        "--directory",
        type=Path,
        help="Explicit installed extension store for selected external providers",
    )
    listing.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    from apizr.scientific_providers.selection import list_providers
    from apizr.workspace.provider_selection import load_selection

    try:
        report = list_providers(
            load_selection(args.selection), directory=args.directory
        )
        if args.format == "json":
            print(report.model_dump_json())
        else:
            for provider in report.providers:
                print(
                    f"{provider.choice.identity.name} {provider.choice.identity.version}: {provider.diagnostic or 'active'}"
                )
                print(
                    "  selected: "
                    + (", ".join(provider.selected_capabilities) or "none")
                )
                if provider.descriptor:
                    print(
                        "  capabilities: " + ", ".join(provider.descriptor.capabilities)
                    )
                    print("  limits: " + provider.descriptor.limits.model_dump_json())
                else:
                    print(
                        "  descriptor/limits: unknown (provider not invoked or unavailable)"
                    )
            if not report.providers:
                print(
                    "No providers selected; all automatic scientific observations are unknown."
                )
    except (OSError, ValueError, TypeError, RecursionError):
        print("apizr providers list: invalid_provider_selection", file=sys.stderr)
        return 2
    return 0
