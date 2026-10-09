"""Compatibility alias for :mod:`apizr.plugins.local._download_worker`."""

import sys

import apizr.plugins.local._download_worker as _implementation
from apizr.plugins.local._download_worker import *  # noqa: F403

sys.modules[__name__] = _implementation
