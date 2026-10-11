"""Compatibility alias for :mod:`apizr.plugins.sync.operations`."""

import sys

import apizr.plugins.sync.operations as _implementation
from apizr.plugins.sync.operations import *  # noqa: F403

sys.modules[__name__] = _implementation
