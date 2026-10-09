"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.environment.python_target as _implementation
from apizr.environment.python_target import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
