"""Compatibility alias for :mod:`apizr.cli.commands.delivery`."""

import sys

import apizr.cli.commands.delivery as _implementation
from apizr.cli.commands.delivery import *  # noqa: F403

sys.modules[__name__] = _implementation
