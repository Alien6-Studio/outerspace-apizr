"""Compatibility alias for :mod:`apizr.plugins.local.models`."""

import sys

import apizr.plugins.local.models as _implementation
from apizr.plugins.local.models import *  # noqa: F403

sys.modules[__name__] = _implementation
