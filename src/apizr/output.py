"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.interfaces.files as _implementation
from apizr.interfaces.files import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
