"""Compatibility facade for :mod:`apizr.plugins.lock`."""

from typing import Any

import apizr.plugins.lock as _implementation
from apizr.plugins.lock import *  # noqa: F403


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


def __dir__() -> list[str]:
    return dir(_implementation)
