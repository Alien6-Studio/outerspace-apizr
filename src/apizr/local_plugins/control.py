"""Compatibility alias for :mod:`apizr.plugins.local.control`."""

import sys

import apizr.plugins.local.control as _implementation
from apizr.plugins.local.control import *  # noqa: F403

sys.modules[__name__] = _implementation
