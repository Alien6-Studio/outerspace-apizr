"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.contracts.analysis as _implementation
from apizr.contracts.analysis import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
