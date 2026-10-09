"""Compatibility alias for :mod:`apizr.plugins.local.store`."""

import sys

import apizr.plugins.local.store as _implementation
from apizr.plugins.local.store import *  # noqa: F403

sys.modules[__name__] = _implementation
