"""Compatibility alias for :mod:`apizr.plugins.catalog.models`."""

import sys

import apizr.plugins.catalog.models as _implementation
from apizr.plugins.catalog.models import *  # noqa: F403

sys.modules[__name__] = _implementation
