"""Core admission of untrusted provider results; no execution or publication."""

from pydantic import JsonValue

from apizr.contracts.json import encode
from apizr.experiments.model import ExperimentValue
from apizr.extension_runtime.protocol import Response
from apizr.scientific_providers.contracts.model import ProviderRequest, ProviderResult

RECOGNIZE_OPERATION = "scientific.recognize"
DESCRIBE_OPERATION = "scientific.describe"


def admit_result(value: object, *, request: ProviderRequest) -> ProviderResult:
    """Revalidate identity, source, capabilities, bounds and canonical evidence."""
    try:
        request = ProviderRequest.model_validate(request)
        if isinstance(value, ProviderResult):
            value = value.model_dump(mode="json")
        raw = encode(value, request.provider.limits.max_result_bytes)
        result = ProviderResult.model_validate_json(raw)
        if (
            result.identity != request.provider.identity
            or result.source != request.source.reference
            or result.source_digest != request.source.digest
        ):
            raise ValueError("provider_identity_or_source_mismatch")
        sections = (
            ("metric_signals", result.metric_signals, result.metric_signals.signals),
            (
                "output_candidates",
                result.output_candidates,
                result.output_candidates.signals,
            ),
            (
                "randomness_controls",
                result.randomness_controls,
                result.randomness_controls.controls,
            ),
            ("input_reads", result.input_reads, result.input_reads.artifacts),
        )
        evidence_count = 0
        diagnostic_count = len(result.diagnostics)
        for capability, section, items in sections:
            if (
                section != type(section)()
                and capability not in request.provider.capabilities
            ):
                raise ValueError("provider_capability_undeclared")
            evidence_count += len(items)
            diagnostic_count += len(section.diagnostics)
            # Signal and diagnostic locations come from the existing evidence models.
            for item in (*items, *section.diagnostics):
                _admit_location(item, request)
        for diagnostic in result.diagnostics:
            _admit_location(diagnostic.location, request)
            if (
                diagnostic.capability is not None
                and diagnostic.capability not in request.provider.capabilities
            ):
                raise ValueError("provider_diagnostic_capability_undeclared")
        if (
            evidence_count > request.provider.limits.max_evidence
            or diagnostic_count > request.provider.limits.max_diagnostics
        ):
            raise ValueError("provider_result_limit")
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("provider_result_invalid") from None


def _admit_location(item: ExperimentValue, request: ProviderRequest) -> None:
    source = getattr(item, "source", None)
    line = getattr(item, "line", None)
    column = getattr(item, "column", None)
    if source is not None and source != request.source.reference:
        raise ValueError("provider_location_source_mismatch")
    if (line is None) != (column is None) or (line is not None and source is None):
        raise ValueError("provider_location_incomplete")
    if (
        line is not None
        and column is not None
        and not request.source.contains_location(line, column)
    ):
        raise ValueError("provider_location_outside_source")


def extension_arguments(request: ProviderRequest) -> dict[str, JsonValue]:
    """Operation-specific arguments for the existing apizr.extension/v1 runtime."""
    return ProviderRequest.model_validate(request).model_dump(mode="json")


def admit_extension_response(
    response: Response, *, request: ProviderRequest
) -> ProviderResult:
    """The existing runtime already binds the request id and enforces process bounds."""
    try:
        response = Response.model_validate(response.model_dump(), strict=True)
        if response.operation != RECOGNIZE_OPERATION:
            raise ValueError("provider_operation_mismatch")
    except ValueError:
        raise ValueError("provider_result_invalid") from None
    return admit_result(response.result, request=request)
