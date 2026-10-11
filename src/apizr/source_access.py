"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.workspace.source_access as _implementation
from apizr.workspace.source_access import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
