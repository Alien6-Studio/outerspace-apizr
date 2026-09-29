"""Compatibility exports of shared input/result contracts and fixed OCI errors."""

from apizr.delivery_results import BuildResult as BuildResult
from apizr.delivery_results import PushResult as PushResult
from apizr.publication_contracts import (
    Authentication as Authentication,
)
from apizr.publication_contracts import (
    BuildRequest as BuildRequest,
)
from apizr.publication_contracts import (
    Docker as Docker,
)
from apizr.publication_contracts import (
    Model as Model,
)
from apizr.publication_contracts import (
    PushRequest as PushRequest,
)


class BuildError(Exception):
    """Fixed diagnostic codes only; never expose Docker logs or argument values."""
