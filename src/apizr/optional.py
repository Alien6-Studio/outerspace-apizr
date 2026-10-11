"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.environment.extras as _implementation
from apizr.environment.extras import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
