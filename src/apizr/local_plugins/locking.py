"""Compatibility alias for :mod:`apizr.plugins.local.locking`."""

import sys

import apizr.plugins.artifacts.requirements as _implementation
from apizr.plugins.artifacts.requirements import *  # noqa: F403

sys.modules[__name__] = _implementation
