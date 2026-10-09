"""Supported interpreter/target policy; generation never transpiles user code."""

import argparse
import sys
from typing import Annotated

from pydantic import AfterValidator

DEFAULT_PYTHON = sys.version_info[:2]
MIN_PYTHON = (3, 11)
MAX_PYTHON = (3, 14)
SUPPORTED_RANGE = "Supported Python targets are 3.11 through 3.14"


def validate_python_target(version: tuple[int, int]) -> tuple[int, int]:
    if not MIN_PYTHON <= version <= MAX_PYTHON:
        raise ValueError(SUPPORTED_RANGE)
    return version


def parse_python_target(value: str) -> tuple[int, int]:
    try:
        major, minor = map(int, value.split("."))
    except ValueError as exc:
        raise ValueError(SUPPORTED_RANGE) from exc
    return validate_python_target((major, minor))


def python_target_argument(value: str) -> str:
    """Keep the CLI's string interface and report invalid targets without a traceback."""
    try:
        parse_python_target(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return value


PythonTarget = Annotated[tuple[int, int], AfterValidator(validate_python_target)]
