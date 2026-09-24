"""CLI selection/presentation for the independent Git input adapter."""

import argparse
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from apizr.git_source import acquire_snapshot
from apizr.repository_cli import apply_project


def add_git_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--git", help="Public HTTPS Git repository; no local root/project"
    )
    parser.add_argument(
        "--ref", help="Required with --git: exact branch, tag or full commit"
    )
    parser.add_argument(
        "--subdir", help="Directory inside the Git snapshot, not a source root"
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
    apply_project(parser, args, exposure=exposure, root_required=args.git is None)


@contextmanager
def input_root(args: argparse.Namespace) -> Generator[Path, None, None]:
    if args.git is None:
        yield args.root
    else:
        with acquire_snapshot(
            args.git, args.ref, subdir=args.subdir if args.subdir is not None else "."
        ) as snapshot:
            print(f"Git snapshot: commit {snapshot.commit}", file=sys.stderr)
            yield snapshot.root
