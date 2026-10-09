"""Compatibility alias for :mod:`apizr.plugins.update.operations`."""

import sys

import apizr.plugins.update.operations as _implementation
from apizr.plugins.update.operations import *  # noqa: F403

sys.modules[__name__] = _implementation
