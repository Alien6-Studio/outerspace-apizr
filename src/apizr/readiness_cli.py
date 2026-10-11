"""Compatibility alias for :mod:`apizr.cli.commands.readiness`."""

import sys

import apizr.cli.commands.readiness as _implementation
from apizr.cli.commands.readiness import *  # noqa: F403

sys.modules[__name__] = _implementation
