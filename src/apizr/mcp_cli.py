"""Compatibility alias for :mod:`apizr.cli.commands.mcp`."""

import sys

import apizr.cli.commands.mcp as _implementation
from apizr.cli.commands.mcp import *  # noqa: F403

sys.modules[__name__] = _implementation
