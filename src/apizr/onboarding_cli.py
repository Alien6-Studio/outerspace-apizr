"""Compatibility alias for :mod:`apizr.cli.commands.onboarding`."""

import sys

import apizr.cli.commands.onboarding as _implementation
from apizr.cli.commands.onboarding import *  # noqa: F403

sys.modules[__name__] = _implementation
