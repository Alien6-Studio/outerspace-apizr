"""Explicit invocation of trusted extensions installed outside the core."""

from .errors import (
    CleanupFailed,
    ExtensionError,
    InvalidInvocation,
    InvocationCancelled,
    InvocationTimeout,
    PluginFailed,
    PrerequisiteMissing,
    ProtocolInvalid,
    SizeLimitExceeded,
)
from .protocol import PROTOCOL, Request, Response
from .supervisor import Limits, invoke_extension

__all__ = [
    "PROTOCOL",
    "Request",
    "Response",
    "Limits",
    "invoke_extension",
    "ExtensionError",
    "InvalidInvocation",
    "PrerequisiteMissing",
    "ProtocolInvalid",
    "PluginFailed",
    "SizeLimitExceeded",
    "InvocationTimeout",
    "InvocationCancelled",
    "CleanupFailed",
]
