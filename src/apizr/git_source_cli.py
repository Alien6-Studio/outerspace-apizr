"""CLI selection/presentation for the independent Git input adapter."""

import argparse
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from apizr.git_source import acquire_snapshot
from apizr.git_source.ssh import is_ssh
from apizr.repository_cli import apply_project


def add_git_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--git", help="HTTPS/SSH Git repository; no local root/project")
    parser.add_argument(
        "--ref", help="Required with --git: exact branch, tag or full commit"
    )
    parser.add_argument(
        "--subdir", help="Directory inside the Git snapshot, not a source root"
    )
    parser.add_argument(
        "--ssh-agent-socket", type=Path, help="Explicit existing SSH agent socket"
    )
    parser.add_argument(
        "--ssh-known-hosts", type=Path, help="Explicit trusted SSH host keys"
    )


def apply_input(
    parser: argparse.ArgumentParser, args: argparse.Namespace, *, exposure: bool = False
) -> None:
    if args.git is not None:
        if args.root is not None or args.project is not None:
            parser.error("--git cannot be combined with a local root or --project")
        if args.ref is None:
            parser.error("--git requires --ref")
    elif args.ref is not None or args.subdir is not None:
        parser.error("--ref and --subdir require --git")
    if args.git is not None and is_ssh(args.git):
        if args.ssh_agent_socket is None or args.ssh_known_hosts is None:
            parser.error("SSH requires --ssh-agent-socket and --ssh-known-hosts")
    elif args.ssh_agent_socket is not None or args.ssh_known_hosts is not None:
        parser.error(
            "--ssh-agent-socket and --ssh-known-hosts require an SSH Git source"
        )
    apply_project(parser, args, exposure=exposure, root_required=args.git is None)


@contextmanager
def input_root(args: argparse.Namespace) -> Generator[Path, None, None]:
    if args.git is None:
        yield args.root
    else:
        with acquire_snapshot(
            args.git,
            args.ref,
            subdir=args.subdir if args.subdir is not None else ".",
            ssh_agent_socket=args.ssh_agent_socket,
            ssh_known_hosts=args.ssh_known_hosts,
        ) as snapshot:
            print(f"Git snapshot: commit {snapshot.commit}", file=sys.stderr)
            yield snapshot.root
