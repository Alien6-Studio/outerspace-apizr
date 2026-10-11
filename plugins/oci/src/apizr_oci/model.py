"""Compatibility exports of shared input/result contracts and fixed OCI errors."""

from apizr.contracts.publication import (
    Authentication as Authentication,
)
from apizr.contracts.publication import (
    BuildRequest as BuildRequest,
)
from apizr.contracts.publication import (
    Docker as Docker,
)
from apizr.contracts.publication import (
    Model as Model,
)
from apizr.contracts.publication import (
    PushRequest as PushRequest,
)
from apizr.contracts.results import BuildResult as BuildResult
from apizr.contracts.results import PushResult as PushResult


class BuildError(Exception):
    """Fixed diagnostic codes only; never expose Docker logs or argument values."""
