"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.legacy.legacy_delivery as _implementation
from apizr.legacy.legacy_delivery import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
