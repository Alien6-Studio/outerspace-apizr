"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.contracts.types as _implementation
from apizr.contracts.types import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
