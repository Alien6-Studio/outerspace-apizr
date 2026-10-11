"""Compatibility alias for :mod:`apizr.cli.commands.generate`."""

import sys

import apizr.cli.commands.generate as _implementation
from apizr.cli.commands.generate import *  # noqa: F403

sys.modules[__name__] = _implementation
