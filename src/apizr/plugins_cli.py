"""Compatibility alias for :mod:`apizr.cli.commands.plugins`."""

import sys

import apizr.cli.commands.plugins as _implementation
from apizr.cli.commands.plugins import *  # noqa: F403

sys.modules[__name__] = _implementation
