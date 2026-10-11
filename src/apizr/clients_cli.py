"""Compatibility alias for :mod:`apizr.cli.commands.clients`."""

import sys

import apizr.cli.commands.clients as _implementation
from apizr.cli.commands.clients import *  # noqa: F403

sys.modules[__name__] = _implementation
