"""Compatibility alias for :mod:`apizr.plugins.lock.tags`."""

import sys

import apizr.plugins.lock.tags as _implementation
from apizr.plugins.lock.tags import *  # noqa: F403

sys.modules[__name__] = _implementation
