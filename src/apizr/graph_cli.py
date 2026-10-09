"""Compatibility alias for :mod:`apizr.cli.commands.graph`."""

import sys

import apizr.cli.commands.graph as _implementation
from apizr.cli.commands.graph import *  # noqa: F403

sys.modules[__name__] = _implementation
