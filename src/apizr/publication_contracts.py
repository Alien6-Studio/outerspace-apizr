"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.contracts.publication as _implementation
from apizr.contracts.publication import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
