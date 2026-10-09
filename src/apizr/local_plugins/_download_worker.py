"""Compatibility alias for :mod:`apizr.plugins.artifacts._download_worker`."""

import sys

import apizr.plugins.artifacts._download_worker as _implementation
from apizr.plugins.artifacts._download_worker import *  # noqa: F403

sys.modules[__name__] = _implementation
