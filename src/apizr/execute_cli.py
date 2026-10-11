"""Compatibility alias for :mod:`apizr.cli.commands.execute`."""

import sys

import apizr.cli.commands.execute as _implementation
from apizr.cli.commands.execute import *  # noqa: F403

sys.modules[__name__] = _implementation
