"""Compatibility alias for :mod:`apizr.plugins.local.retirement`."""

import sys

import apizr.plugins.local.retirement as _implementation
from apizr.plugins.local.retirement import *  # noqa: F403

sys.modules[__name__] = _implementation
