"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.legacy.prompt as _implementation
from apizr.legacy.prompt import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
