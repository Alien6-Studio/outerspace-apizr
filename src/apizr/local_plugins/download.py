"""Compatibility alias for :mod:`apizr.plugins.local.download`."""

import sys

import apizr.plugins.local.download as _implementation
from apizr.plugins.local.download import *  # noqa: F403

sys.modules[__name__] = _implementation
