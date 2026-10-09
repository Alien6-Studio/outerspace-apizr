"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.contracts.results as _implementation
from apizr.contracts.results import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
