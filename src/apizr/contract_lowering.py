"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.contracts.lowering as _implementation
from apizr.contracts.lowering import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
