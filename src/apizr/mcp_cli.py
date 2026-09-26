"""Dedicated stdio launcher; the optional SDK never enters the core process."""

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from apizr.extension_runtime import ExtensionError
from apizr.local_plugins import PluginError, resolve_active_extension
from apizr.user_config import plugins_directory


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="apizr mcp")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser(
        "serve", help="Serve local read-only analysis over stdio"
    )
    serve.add_argument("--project", type=Path, required=True)
    serve.add_argument("--plugins-dir", type=Path)
    serve.add_argument("--user-config", type=Path)
    serve.add_argument("--timeout-ms", type=int, default=10000)
    serve.add_argument("--max-request-bytes", type=int, default=65536)
    serve.add_argument("--max-response-bytes", type=int, default=4194304)
    args = parser.parse_args(argv)
    try:
        if not args.project.is_absolute():
            raise PluginError("absolute_project_required")
        directory = plugins_directory(args.plugins_dir, args.user_config)
        record = resolve_active_extension("apizr-mcp", directory=directory)
        if record.module != "apizr_mcp":
            raise PluginError("mcp_entrypoint_mismatch")
        # Replace this process, preserving the client's stdio/signals. No shell,
        # parent secrets, plugin import, or extension-protocol envelope is used.
        os.execve(
            record.python,
            [
                record.python,
                "-I",
                "-B",
                "-m",
                record.module,
                "serve",
                "--project",
                str(args.project),
                "--timeout-ms",
                str(args.timeout_ms),
                "--max-request-bytes",
                str(args.max_request_bytes),
                "--max-response-bytes",
                str(args.max_response_bytes),
            ],
            {},
        )
    except (PluginError, ExtensionError) as error:
        print(f"apizr mcp: {error}", file=sys.stderr)
    except OSError:
        print("apizr mcp: launch_failed", file=sys.stderr)
    return 2
