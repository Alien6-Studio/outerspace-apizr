"""Compatibility alias for :mod:`apizr.plugins.local.locking`."""

import sys

import apizr.plugins.local.locking as _implementation
from apizr.plugins.local.locking import *  # noqa: F403

sys.modules[__name__] = _implementation
