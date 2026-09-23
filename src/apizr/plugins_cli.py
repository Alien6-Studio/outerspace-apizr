"""Argument parsing and presentation for explicitly installed local extensions."""

import argparse
import sys
from pathlib import Path
from typing import Sequence

from apizr.extension_runtime import ExtensionError, InvocationCancelled, Limits
from apizr.local_plugins import (
    DownloadCancelled,
    PluginError,
    disable_extension,
    enable_extension,
    install_from_source,
    list_extensions,
    read_arguments,
    run_extension,
)


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="apizr plugins")
    commands = parser.add_subparsers(dest="command", required=True)
    install = commands.add_parser(
        "install", help="Install a trusted local or HTTPS wheel by its SHA-256"
    )
    install.add_argument("wheel", help="Local wheel path or HTTPS URL")
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
    listing.add_argument(
        "--active", action="store_true", help="List only explicitly active versions"
    )
    enable = commands.add_parser("enable", help="Select an exact installed version")
    enable.add_argument("name")
    enable.add_argument("--version", required=True)
    disable = commands.add_parser("disable", help="Block future calls to a plugin")
    disable.add_argument("name")
    run = commands.add_parser(
        "run", help="Explicitly invoke an active installed plugin"
    )
    run.add_argument("name")
    run.add_argument("operation")
    run.add_argument(
        "--arguments", type=Path, required=True, help="Bounded JSON object file"
    )
    for command in (install, listing, enable, disable, run):
        command.add_argument(
            "--plugins-dir",
            type=Path,
            help="Explicit user storage directory (also for disposable tests)",
        )
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            installed = install_from_source(
                args.wheel, args.sha256, directory=args.plugins_dir, python=args.python
            )
            print(f"Installed {installed.name} {installed.version}")
        elif args.command == "enable":
            selected = enable_extension(
                args.name, args.version, directory=args.plugins_dir
            )
            print(f"Enabled {selected.name} {selected.version}")
        elif args.command == "disable":
            disable_extension(args.name, directory=args.plugins_dir)
            print("Plugin disabled.")
        elif args.command == "run":
            limits = Limits()
            response = run_extension(
                args.name,
                args.operation,
                read_arguments(args.arguments, limits=limits),
                directory=args.plugins_dir,
                limits=limits,
            )
            print(response.model_dump_json())
        else:
            inventory = list_extensions(directory=args.plugins_dir, active=args.active)
            if args.json:
                print(inventory.model_dump_json(by_alias=True))
            elif not inventory.installations:
                print("No local extensions installed.")
            else:
                for item in inventory.installations:
                    print(f"{item.name} {item.version}  {item.protocol}  {item.module}")
        return 0
    except (InvocationCancelled, DownloadCancelled) as error:
        print(f"apizr plugins: {error}", file=sys.stderr)
        return 130
    except (PluginError, ExtensionError) as error:
        print(f"apizr plugins: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        reason = (
            "installation_interrupted" if args.command == "install" else "cancelled"
        )
        print(f"apizr plugins: {reason}", file=sys.stderr)
        return 130
