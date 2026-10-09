"""Compatibility facade for :mod:`apizr.plugins.update`."""

from typing import Any

import apizr.plugins.update as _implementation
from apizr.plugins.update import *  # noqa: F403


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


def __dir__() -> list[str]:
    return dir(_implementation)
