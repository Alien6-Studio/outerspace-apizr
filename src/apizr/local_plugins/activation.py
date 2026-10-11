"""Compatibility alias for :mod:`apizr.plugins.local.activation`."""

import sys

import apizr.plugins.local.activation as _implementation
from apizr.plugins.local.activation import *  # noqa: F403

sys.modules[__name__] = _implementation
