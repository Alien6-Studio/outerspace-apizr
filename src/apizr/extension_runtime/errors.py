"""Stable, redacted invocation failures; no plugin text or argument values."""

from typing import Literal


class ExtensionError(Exception):
    code = "extension_error"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidInvocation(ExtensionError):
    code = "invalid_invocation"


class PrerequisiteMissing(ExtensionError):
    code = "prerequisite_missing"


class ProtocolInvalid(ExtensionError):
    code = "protocol_invalid"


class PluginFailed(ExtensionError):
    code = "plugin_failed"


class SizeLimitExceeded(ExtensionError):
    code = "size_limit"

    def __init__(self, stream: Literal["request", "stdout", "stderr"]) -> None:
        self.stream = stream
        super().__init__()


class InvocationTimeout(ExtensionError):
    code = "timeout"


class InvocationCancelled(ExtensionError):
    code = "cancelled"


class CleanupFailed(ExtensionError):
    code = "cleanup_failed"
