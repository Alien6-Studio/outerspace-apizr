"""Compatibility alias for :mod:`apizr.workspace.project`."""

import sys

import apizr.workspace.project as _implementation
from apizr.workspace.project import *  # noqa: F403

sys.modules[__name__] = _implementation
