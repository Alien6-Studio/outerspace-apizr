"""Compatibility alias for :mod:`apizr.cli.completion_spec`."""

import sys

import apizr.cli.completion_spec as _implementation
from apizr.cli.completion_spec import *  # noqa: F403

sys.modules[__name__] = _implementation
