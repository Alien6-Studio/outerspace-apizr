"""Compatibility alias for :mod:`apizr.workspace.files`."""

import sys

import apizr.workspace.files as _implementation
from apizr.workspace.files import *  # noqa: F403

sys.modules[__name__] = _implementation
