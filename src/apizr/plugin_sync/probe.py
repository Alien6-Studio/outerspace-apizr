"""Compatibility alias for :mod:`apizr.plugins.sync.probe`."""

import sys

import apizr.plugins.sync.probe as _implementation
from apizr.plugins.sync.probe import *  # noqa: F403

sys.modules[__name__] = _implementation
