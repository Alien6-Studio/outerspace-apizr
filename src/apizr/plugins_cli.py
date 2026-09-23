"""Argument parsing and presentation for explicitly installed local extensions."""

import argparse
import sys
from pathlib import Path
from typing import Sequence

from apizr.local_plugins import PluginError, install_extension, list_extensions


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="apizr plugins")
    commands = parser.add_subparsers(dest="command", required=True)
    install = commands.add_parser(
        "install", help="Install a trusted local wheel offline"
    )
    install.add_argument("wheel", type=Path)
    install.add_argument(
        "--sha256",
        required=True,
        help="Expected wheel SHA-256 (integrity, not author trust)",
    )
    install.add_argument(
        "--python", type=Path, help="Absolute path to an already installed Python"
    )
    listing = commands.add_parser("list", help="Read the local installation inventory")
    listing.add_argument(
        "--json", action="store_true", help="Emit the versioned inventory"
    )
    for command in (install, listing):
        command.add_argument(
            "--plugins-dir",
            type=Path,
            help="Explicit user storage directory (also for disposable tests)",
        )
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            installed = install_extension(
                args.wheel, args.sha256, directory=args.plugins_dir, python=args.python
            )
            print(f"Installed {installed.name} {installed.version}")
        else:
            inventory = list_extensions(directory=args.plugins_dir)
            if args.json:
                print(inventory.model_dump_json(by_alias=True))
            elif not inventory.installations:
                print("No local extensions installed.")
            else:
                for item in inventory.installations:
                    print(f"{item.name} {item.version}  {item.protocol}  {item.module}")
        return 0
    except PluginError as error:
        print(f"apizr plugins: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("apizr plugins: installation_interrupted", file=sys.stderr)
        return 130
