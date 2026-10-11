"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.contracts.json as _implementation
from apizr.contracts.json import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
