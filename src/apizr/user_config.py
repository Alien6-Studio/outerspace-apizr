"""Compatibility alias for :mod:`apizr.workspace.user`."""

import sys

import apizr.workspace.user as _implementation
from apizr.workspace.user import *  # noqa: F403

sys.modules[__name__] = _implementation
