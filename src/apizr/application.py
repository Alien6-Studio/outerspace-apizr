"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.contracts.application as _implementation
from apizr.contracts.application import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
