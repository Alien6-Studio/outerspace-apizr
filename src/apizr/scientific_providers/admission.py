"""Compatibility exports for bounded scientific result admission."""

from .contracts.admission import (
    DESCRIBE_OPERATION,
    RECOGNIZE_OPERATION,
    admit_extension_response,
    admit_result,
    extension_arguments,
)

__all__ = [
    "DESCRIBE_OPERATION",
    "RECOGNIZE_OPERATION",
    "admit_extension_response",
    "admit_result",
    "extension_arguments",
]
