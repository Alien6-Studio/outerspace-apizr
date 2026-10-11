"""Compatibility alias for :mod:`apizr.cli.completion`."""

import sys

import apizr.cli.completion as _implementation
from apizr.cli.completion import *  # noqa: F403

sys.modules[__name__] = _implementation
