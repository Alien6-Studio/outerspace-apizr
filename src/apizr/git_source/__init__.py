"""Static public HTTPS Git input; no plugins or optional dependencies."""

from .acquisition import acquire_snapshot
from .models import AcquisitionLimits, GitSnapshot, GitSourceError

__all__ = ["AcquisitionLimits", "GitSnapshot", "GitSourceError", "acquire_snapshot"]
