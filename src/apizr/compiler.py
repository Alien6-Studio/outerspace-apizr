"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.workspace.compiler as _implementation
from apizr.workspace.compiler import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
