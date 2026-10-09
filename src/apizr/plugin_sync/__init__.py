"""Compatibility facade for :mod:`apizr.plugins.sync`."""

from typing import Any

import apizr.plugins.sync as _implementation
from apizr.plugins.sync import *  # noqa: F403


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


def __dir__() -> list[str]:
    return dir(_implementation)
