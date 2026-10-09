"""Compatibility alias for :mod:`apizr.cli.commands.scan`."""

import sys

import apizr.cli.commands.scan as _implementation
from apizr.cli.commands.scan import *  # noqa: F403

sys.modules[__name__] = _implementation
