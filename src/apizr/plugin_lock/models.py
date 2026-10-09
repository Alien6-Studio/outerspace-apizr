"""Compatibility alias for :mod:`apizr.plugins.lock.models`."""

import sys

import apizr.plugins.lock.models as _implementation
from apizr.plugins.lock.models import *  # noqa: F403

sys.modules[__name__] = _implementation
