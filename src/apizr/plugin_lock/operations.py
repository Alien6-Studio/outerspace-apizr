"""Compatibility alias for :mod:`apizr.plugins.lock.operations`."""

import sys

import apizr.plugins.lock.operations as _implementation
from apizr.plugins.lock.operations import *  # noqa: F403

sys.modules[__name__] = _implementation
