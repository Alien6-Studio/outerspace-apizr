"""Compatibility alias for :mod:`apizr.plugins.local.wheel`."""

import sys

import apizr.plugins.artifacts.wheel as _implementation
from apizr.plugins.artifacts.wheel import *  # noqa: F403

sys.modules[__name__] = _implementation
