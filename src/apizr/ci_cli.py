"""Public, non-effectful CI command; no forge environment or API access."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn, cast

from apizr.ci import CIError, Operation, execute
from apizr.operator_policy import AuthorizationDenied


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise CIError("ci_arguments_invalid")


def main(argv: Sequence[str]) -> int:
    parser = Parser(
        prog="apizr ci",
        allow_abbrev=False,
        description="Static CI check or REST/MCP bundle build.",
    )
    parser.add_argument("operation", choices=("check", "build-rest", "build-mcp"))
    parser.add_argument("--project", type=Path, default=Path("apizr.toml"))
    parser.add_argument("--output-dir", type=Path, default=Path(".apizr-ci"))
    authority = parser.add_mutually_exclusive_group(required=True)
    authority.add_argument("--operator-policy", type=Path)
    authority.add_argument("--authorize-project-analysis", action="store_true")
    try:
        args = parser.parse_args(argv)
        result = execute(
            cast(Operation, args.operation),
            project=args.project,
            output_dir=args.output_dir,
            operator_policy=args.operator_policy,
            authorize_project_analysis=args.authorize_project_analysis,
        )
        print(result.diagnostic)
        return result.exit_code
    except KeyboardInterrupt:
        print("ci_cancelled", file=sys.stderr)
        return 130
    except CIError as error:
        print(str(error), file=sys.stderr)
        return 2
    except AuthorizationDenied:
        print("ci_authorization_refused", file=sys.stderr)
        return 2
    except (ValueError, OSError, RecursionError, UnicodeError):
        print("ci_configuration_invalid", file=sys.stderr)
        return 2
