"""Compatibility alias for :mod:`apizr.plugins.local.backend`."""

import sys

import apizr.plugins.local.backend as _implementation
from apizr.plugins.local.backend import *  # noqa: F403

sys.modules[__name__] = _implementation
