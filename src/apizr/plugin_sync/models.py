"""Compatibility alias for :mod:`apizr.plugins.sync.models`."""

import sys

import apizr.plugins.sync.models as _implementation
from apizr.plugins.sync.models import *  # noqa: F403

sys.modules[__name__] = _implementation
