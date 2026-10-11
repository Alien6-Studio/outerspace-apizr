"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.generators.notebooks as _implementation
from apizr.generators.notebooks import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
