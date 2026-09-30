"""Dedicated stdio launcher; the optional SDK never enters the core process."""

import argparse
import os
import sys
import tempfile
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Sequence

from apizr.analysis_session import MAX_SESSION_BYTES, load_scope
from apizr.extension_runtime import ExtensionError
from apizr.local_plugins import PluginError
from apizr.local_plugins.activation import admitted_extension
from apizr.local_plugins.models import Installation
from apizr.local_plugins.store import storage_directory
from apizr.mcp_session import DeliverySession, McpSession, load_delivery_request
from apizr.operator_policy import AuthorizationDenied, load_operator_policy
from apizr.user_config import plugins_directory


@contextmanager
def _admitted_mcp(directory: Path | None) -> Generator[tuple[Installation, int]]:
    """Prefer the official distribution; retain existing local installations.

    An installed but inactive or invalid new identity must not fall back to an
    older identity. Admission continues to own the existing process lease.
    """
    with ExitStack() as stack:
        try:
            admitted = stack.enter_context(
                admitted_extension(
                    "outerspace-apizr-mcp", directory=directory, inherit=True
                )
            )
        except PluginError as error:
            if str(error) != "plugin_not_installed":
                raise
            admitted = stack.enter_context(
                admitted_extension("apizr-mcp", directory=directory, inherit=True)
            )
        yield admitted


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="apizr mcp")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser(
        "serve", help="Serve local analysis and explicitly selected delivery over stdio"
    )
    serve.add_argument("--project", type=Path, required=True)
    serve.add_argument("--operator-policy", type=Path)
    serve.add_argument("--delivery-request", type=Path)
    serve.add_argument("--plugins-dir", type=Path)
    serve.add_argument("--user-config", type=Path)
    serve.add_argument("--timeout-ms", type=int, default=10000)
    serve.add_argument("--max-request-bytes", type=int, default=65536)
    serve.add_argument("--max-response-bytes", type=int, default=4194304)
    args = parser.parse_args(argv)
    try:
        if not args.project.is_absolute():
            raise PluginError("absolute_project_required")
        if args.delivery_request is not None and args.operator_policy is None:
            print("apizr mcp: delivery_policy_required", file=sys.stderr)
            return 2
        authority = (
            load_operator_policy(args.operator_policy) if args.operator_policy else None
        )
        scope = load_scope(args.project, authority)
        raw = scope.model_dump_json().encode()
        directory = plugins_directory(args.plugins_dir, args.user_config)
        if args.delivery_request is not None:
            request = load_delivery_request(args.delivery_request)
            directory = storage_directory(directory)
            raw = (
                McpSession(
                    analysis=scope,
                    delivery=DeliverySession(
                        request=request, plugins_dir=str(directory)
                    ),
                )
                .model_dump_json(by_alias=True)
                .encode()
            )
        if len(raw) > MAX_SESSION_BYTES:
            raise ValueError("session_too_large")
        with (
            tempfile.TemporaryFile() as session,
            _admitted_mcp(directory) as (
                record,
                _,
            ),
        ):
            if record.module != "apizr_mcp":
                raise PluginError("mcp_entrypoint_mismatch")
            session.write(raw)
            session.flush()
            session.seek(0)
            os.set_inheritable(session.fileno(), True)
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
                    "--session-fd",
                    str(session.fileno()),
                    "--timeout-ms",
                    str(args.timeout_ms),
                    "--max-request-bytes",
                    str(args.max_request_bytes),
                    "--max-response-bytes",
                    str(args.max_response_bytes),
                ],
                {},
            )
    except AuthorizationDenied as error:
        print(error.decision.model_dump_json(by_alias=True), file=sys.stderr)
    except (ValueError, RecursionError):
        print(
            "apizr mcp: "
            + (
                "invalid_delivery_configuration"
                if args.delivery_request is not None
                else "invalid_analysis_configuration"
            ),
            file=sys.stderr,
        )
    except (PluginError, ExtensionError) as error:
        print(f"apizr mcp: {error}", file=sys.stderr)
    except OSError:
        print("apizr mcp: launch_failed", file=sys.stderr)
    return 2
