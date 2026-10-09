"""Compatibility alias for :mod:`apizr.cli.commands.git_source`."""

import sys

import apizr.cli.commands.git_source as _implementation
from apizr.cli.commands.git_source import *  # noqa: F403

sys.modules[__name__] = _implementation
