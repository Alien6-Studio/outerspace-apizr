"""Compatibility alias for :mod:`apizr.plugins.local.usage`."""

import sys

import apizr.plugins.local.usage as _implementation
from apizr.plugins.local.usage import *  # noqa: F403

sys.modules[__name__] = _implementation
