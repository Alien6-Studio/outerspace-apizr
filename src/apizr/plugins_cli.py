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
from apizr.plugin_lock import LockError, Result, check_lock, create_lock
from apizr.plugin_lock.models import Diagnostic
from apizr.user_config import plugins_directory


def timeout_ms(value: str) -> int:
    try:
        return Limits(wall_time_ms=int(value)).wall_time_ms
    except ValueError:
        raise argparse.ArgumentTypeError(
            "expected an integer from 1 to 600000 ms"
        ) from None


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
    install.add_argument(
        "--requirements", type=Path, help="Exact versions and SHA-256 requirements lock"
    )
    install.add_argument(
        "--wheelhouse",
        type=Path,
        help="Local wheel directory (requires --requirements)",
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
    run.add_argument(
        "--timeout-ms",
        type=timeout_ms,
        default=Limits().wall_time_ms,
        help="Explicit invocation deadline in milliseconds (1–600000; default 10000)",
    )
    lock = commands.add_parser(
        "lock", help="Create or check portable project artifact locks"
    )
    lock_commands = lock.add_subparsers(dest="lock_command", required=True)
    create = lock_commands.add_parser(
        "create", help="Validate local artifacts and write a new lock"
    )
    check = lock_commands.add_parser(
        "check", help="Check artifacts without rewriting the lock"
    )
    create.add_argument("--output", type=Path, required=True)
    check.add_argument("--lock", type=Path, required=True)
    check.add_argument("--installed", action="store_true")
    for command in (create, check):
        command.add_argument("--project", type=Path, required=True)
        command.add_argument("--wheelhouse", type=Path, required=True)
        command.add_argument("--json", action="store_true")
    for command in (install, listing, enable, disable, run, create, check):
        command.add_argument(
            "--user-config", type=Path, help="Explicit operator preferences file"
        )
        command.add_argument(
            "--plugins-dir",
            type=Path,
            help="Explicit user storage directory (also for disposable tests)",
        )
    args = parser.parse_args(argv)
    try:
        args.plugins_dir = plugins_directory(args.plugins_dir, args.user_config)
        if args.command == "lock":
            result = (
                create_lock(args.project, args.wheelhouse, args.output)
                if args.lock_command == "create"
                else check_lock(
                    args.project,
                    args.lock,
                    args.wheelhouse,
                    installed=args.installed,
                    directory=args.plugins_dir,
                )
            )
            _show_lock(result, args.json)
            return 0 if result.valid else 1
        if args.command == "install":
            installed = install_from_source(
                args.wheel,
                args.sha256,
                directory=args.plugins_dir,
                python=args.python,
                requirements=args.requirements,
                wheelhouse=args.wheelhouse,
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
            limits = Limits(wall_time_ms=args.timeout_ms)
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
    except LockError as error:
        if args.json:
            _show_lock(
                Result(valid=False, diagnostics=(Diagnostic(code=error.code),)), True
            )
        print(f"apizr plugins: {error.code}", file=sys.stderr)
        return 2
    except (InvocationCancelled, DownloadCancelled) as error:
        print(f"apizr plugins: {error}", file=sys.stderr)
        return 130
    except (PluginError, ExtensionError) as error:
        if args.command == "lock" and args.json:
            _show_lock(
                Result(valid=False, diagnostics=(Diagnostic(code=str(error)),)), True
            )
        print(f"apizr plugins: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        reason = (
            "installation_interrupted" if args.command == "install" else "cancelled"
        )
        print(f"apizr plugins: {reason}", file=sys.stderr)
        return 130


def _show_lock(result: Result, as_json: bool) -> None:
    if as_json:
        print(result.model_dump_json())
    else:
        print("Plugin lock valid." if result.valid else "Plugin lock differs.")
        for diagnostic in result.diagnostics:
            print(
                f"{diagnostic.code}: {diagnostic.plugin or '-'} / {diagnostic.distribution or '-'}"
            )
