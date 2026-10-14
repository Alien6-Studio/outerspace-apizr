"""Bounded scientific evidence provider contracts and recognition."""

from .admission import (
    DESCRIBE_OPERATION,
    RECOGNIZE_OPERATION,
    admit_extension_response,
    admit_result,
    extension_arguments,
)
from .contracts import (
    ProducerIdentity,
    ProviderDescriptor,
    ProviderDiagnostic,
    ProviderLimits,
    ProviderLocation,
    ProviderRequest,
    ProviderResult,
    SDKAdapter,
    SDKAdapterDescriptor,
    SDKReporter,
    StaticProvider,
)

__all__ = [
    "DESCRIBE_OPERATION",
    "RECOGNIZE_OPERATION",
    "admit_extension_response",
    "admit_result",
    "extension_arguments",
    "ProducerIdentity",
    "ProviderDescriptor",
    "ProviderDiagnostic",
    "ProviderLimits",
    "ProviderLocation",
    "ProviderRequest",
    "ProviderResult",
    "SDKAdapter",
    "SDKAdapterDescriptor",
    "SDKReporter",
    "StaticProvider",
]
