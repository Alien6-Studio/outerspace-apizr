"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.contracts.delivery as _implementation
from apizr.contracts.delivery import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
