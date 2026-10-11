"""Compatibility alias for :mod:`apizr.plugins.local.operations`."""

import sys

import apizr.plugins.local.operations as _implementation
from apizr.plugins.local.operations import *  # noqa: F403

sys.modules[__name__] = _implementation
