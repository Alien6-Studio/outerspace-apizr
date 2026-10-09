"""Compatibility alias for :mod:`apizr.cli.commands.repository_readiness`."""

import sys

import apizr.cli.commands.repository_readiness as _implementation
from apizr.cli.commands.repository_readiness import *  # noqa: F403

sys.modules[__name__] = _implementation
