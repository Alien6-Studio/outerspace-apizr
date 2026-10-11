"""Compatibility alias for :mod:`apizr.plugins.update.models`."""

import sys

import apizr.plugins.update.models as _implementation
from apizr.plugins.update.models import *  # noqa: F403

sys.modules[__name__] = _implementation
