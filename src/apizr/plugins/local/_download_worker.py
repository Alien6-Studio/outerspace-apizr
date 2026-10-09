"""Compatibility forwarding to the canonical implementation."""

import sys

import apizr.plugins.artifacts._download_worker as _implementation
from apizr.plugins.artifacts._download_worker import *  # noqa: F403 - historical public exports

sys.modules[__name__] = _implementation
