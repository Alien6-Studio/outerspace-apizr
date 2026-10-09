"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.workspace.analysis_session as _implementation
from apizr.workspace.analysis_session import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
