"""Compatibility alias for :mod:`apizr.cli.commands.ci`."""

import sys

import apizr.cli.commands.ci as _implementation
from apizr.cli.commands.ci import *  # noqa: F403

sys.modules[__name__] = _implementation
