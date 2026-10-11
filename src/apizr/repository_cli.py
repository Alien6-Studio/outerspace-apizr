"""Compatibility alias for :mod:`apizr.cli.commands.repository`."""

import sys

import apizr.cli.commands.repository as _implementation
from apizr.cli.commands.repository import *  # noqa: F403

sys.modules[__name__] = _implementation
