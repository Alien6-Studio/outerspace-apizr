"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.legacy.configuration as _implementation
from apizr.legacy.configuration import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
