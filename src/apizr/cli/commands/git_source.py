"""CLI selection/presentation for the independent Git input adapter."""

import argparse
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from apizr.analysis_contracts import GitAnalysisTarget
from apizr.cli.commands.repository import apply_project
from apizr.git_source import acquire_snapshot
from apizr.git_source.contracts import GitTarget, validate_source
from apizr.git_source.ssh import is_ssh
from apizr.operator_policy import (
    AuthorizationDenied,
    OperatorPolicy,
    decide_analysis,
    decide_git,
    load_operator_policy,
)
from apizr.source_access import RepositoryInput


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
def input_root(
    args: argparse.Namespace,
) -> Generator[tuple[RepositoryInput, OperatorPolicy | None], None, None]:
    authority = (
        load_operator_policy(args.operator_policy)
        if args.operator_policy is not None
        else None
    )
    if args.git is None:
        yield args.root, authority
    else:
        repository, reference = args.git, args.ref
        subdir = args.subdir if args.subdir is not None else "."
        agent = (
            args.ssh_agent_socket.absolute()
            if args.ssh_agent_socket is not None
            else None
        )
        known = (
            args.ssh_known_hosts.absolute()
            if args.ssh_known_hosts is not None
            else None
        )
        transport = validate_source(repository, reference, subdir, None, agent, known)
        fetch = GitTarget(
            transport=transport,
            repository=repository,
            reference=reference,
            subdir=subdir,
            ssh_agent_socket=str(agent) if agent is not None else None,
            ssh_known_hosts=str(known) if known is not None else None,
        )
        decision = decide_git(authority, fetch)
        if not decision.allowed:
            raise AuthorizationDenied(decision.code)
        source = GitAnalysisTarget(
            repository=repository, reference=reference, subdir=subdir
        )
        decision = decide_analysis(authority, source)
        if not decision.allowed:
            raise AuthorizationDenied(decision.code)
        with acquire_snapshot(
            source.repository,
            source.reference,
            subdir=source.subdir,
            ssh_agent_socket=agent,
            ssh_known_hosts=known,
            operator_policy=authority,
        ) as snapshot:
            print(f"Git snapshot: commit {snapshot.commit}", file=sys.stderr)
            yield snapshot, authority
