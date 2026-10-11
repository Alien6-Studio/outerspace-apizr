"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.workspace.application_resources as _implementation
from apizr.workspace.application_resources import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
