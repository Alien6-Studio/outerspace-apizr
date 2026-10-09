"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.capabilities.inspection as _implementation
from apizr.capabilities.inspection import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
