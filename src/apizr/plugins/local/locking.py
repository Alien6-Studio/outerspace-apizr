"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.plugins.artifacts.requirements as _implementation
from apizr.plugins.artifacts.requirements import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
