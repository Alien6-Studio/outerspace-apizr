"""Compatibility alias for :mod:`apizr.plugins.catalog.generation`."""

import sys

import apizr.plugins.catalog.generation as _implementation
from apizr.plugins.catalog.generation import *  # noqa: F403

sys.modules[__name__] = _implementation
