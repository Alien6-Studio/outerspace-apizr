"""Registry entry point for the existing, explicitly activated stdio server."""

import sys

from apizr.cli.commands.mcp import main as serve


def main() -> int:
    return serve(["serve", *sys.argv[1:]])
