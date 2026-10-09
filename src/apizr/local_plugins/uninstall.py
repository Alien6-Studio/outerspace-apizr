"""Compatibility alias for :mod:`apizr.plugins.local.uninstall`."""

import sys

import apizr.plugins.local.uninstall as _implementation
from apizr.plugins.local.uninstall import *  # noqa: F403

sys.modules[__name__] = _implementation
