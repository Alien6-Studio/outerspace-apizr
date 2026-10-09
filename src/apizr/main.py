"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.legacy.main as _implementation
from apizr.legacy.main import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation

if __name__ == "__main__":
    _implementation.main()
