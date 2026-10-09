"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.legacy.app as _implementation
from apizr.legacy.app import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
