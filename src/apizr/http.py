"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.legacy.http as _implementation
from apizr.legacy.http import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
