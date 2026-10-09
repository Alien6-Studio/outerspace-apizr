"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.workspace.operator_policy as _implementation
from apizr.workspace.operator_policy import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
