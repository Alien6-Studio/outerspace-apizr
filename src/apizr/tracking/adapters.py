"""Narrow reporting surface for an explicitly invoked in-process SDK adapter."""

from apizr.scientific_providers.contracts import SDKAdapterDescriptor, SDKCapability
from apizr.tracking.session import (
    TrackingError,
    log_artifact,
    log_input,
    log_metric,
    log_parameter,
)


class AdapterReporter:
    """Reporting delegates to the current ordinary session and its existing bounds."""

    def __init__(self, descriptor: SDKAdapterDescriptor) -> None:
        self._descriptor = SDKAdapterDescriptor.model_validate(descriptor)

    def _require(self, capability: SDKCapability) -> None:
        if capability not in self._descriptor.capabilities:
            raise TrackingError("tracking_adapter_capability_undeclared")

    def log_parameter(self, name: str, value: object) -> None:
        self._require("parameter")
        log_parameter(name, value)

    def log_metric(self, name: str, value: object, *, unit: str | None = None) -> None:
        self._require("metric")
        log_metric(name, value, unit=unit)

    def log_input(
        self, name: str, reference: str | None = None, *, uri: str | None = None
    ) -> None:
        self._require("input")
        log_input(name, reference, uri=uri)

    def log_artifact(
        self, name: str, reference: str, *, media_type: str | None = None
    ) -> None:
        self._require("artifact")
        log_artifact(name, reference, media_type=media_type)
