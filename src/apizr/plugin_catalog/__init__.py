"""Compatibility facade for :mod:`apizr.plugins.catalog`."""

from typing import Any

import apizr.plugins.catalog as _implementation
from apizr.plugins.catalog import *  # noqa: F403


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


def __dir__() -> list[str]:
    return dir(_implementation)
