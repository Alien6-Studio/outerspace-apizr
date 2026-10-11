"""Compatibility alias for :mod:`apizr.plugins.sync.preparation`."""

import sys

import apizr.plugins.sync.preparation as _implementation
from apizr.plugins.sync.preparation import *  # noqa: F403

sys.modules[__name__] = _implementation
