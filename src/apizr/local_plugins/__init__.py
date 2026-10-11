"""Compatibility facade for :mod:`apizr.plugins.local`."""

from typing import Any

import apizr.plugins.local as _implementation
from apizr.plugins.local import *  # noqa: F403


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


def __dir__() -> list[str]:
    return dir(_implementation)
