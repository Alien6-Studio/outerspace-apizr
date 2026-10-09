"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.plugins.artifacts.wheel as _implementation
from apizr.plugins.artifacts.wheel import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
