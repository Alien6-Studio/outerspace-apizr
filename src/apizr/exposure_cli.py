"""Compatibility alias for :mod:`apizr.cli.commands.exposure`."""

import sys

import apizr.cli.commands.exposure as _implementation
from apizr.cli.commands.exposure import *  # noqa: F403

sys.modules[__name__] = _implementation
