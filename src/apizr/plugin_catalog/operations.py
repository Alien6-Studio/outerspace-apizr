"""Compatibility alias for :mod:`apizr.plugins.catalog.operations`."""

import sys

import apizr.plugins.catalog.operations as _implementation
from apizr.plugins.catalog.operations import *  # noqa: F403

sys.modules[__name__] = _implementation
