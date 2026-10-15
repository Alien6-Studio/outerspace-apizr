"""Explicit contract adapter for the official built-in lexical recognizers."""

from apizr.experiments.inputs import InputResult
from apizr.experiments.metrics import MetricDiscoveryResult
from apizr.experiments.outputs import OutputDiscoveryResult
from apizr.experiments.randomness import RandomnessResult
from apizr.scientific_providers.builtin.inputs import discover_inputs
from apizr.scientific_providers.builtin.metrics import discover_metrics
from apizr.scientific_providers.builtin.outputs import discover_outputs
from apizr.scientific_providers.builtin.randomness import discover_randomness
from apizr.scientific_providers.contracts import (
    ProducerIdentity,
    ProviderDescriptor,
    ProviderRequest,
    ProviderResult,
    admit_result,
)


class BuiltinProvider:
    """Reference StaticProvider; caller-selected capabilities share request ceilings.

    The compatibility discovery functions retain their individual historical
    limits. Contract consumers additionally enforce the aggregate request limits.
    """

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            identity=ProducerIdentity(name="apizr.builtin", version="1"),
            capabilities=(
                "metric_signals",
                "output_candidates",
                "randomness_controls",
                "input_reads",
            ),
        )

    def recognize(self, request: ProviderRequest) -> ProviderResult:
        request = ProviderRequest.model_validate(request)
        if request.provider.identity != self.descriptor.identity:
            raise ValueError("provider_identity_mismatch")
        source = request.source.text
        reference = request.source.reference
        capabilities = request.provider.capabilities
        result = ProviderResult(
            identity=self.descriptor.identity,
            source=reference,
            source_digest=request.source.digest,
            metric_signals=discover_metrics(source, source_reference=reference)
            if "metric_signals" in capabilities
            else MetricDiscoveryResult(),
            output_candidates=discover_outputs(source, source_reference=reference)
            if "output_candidates" in capabilities
            else OutputDiscoveryResult(),
            randomness_controls=discover_randomness(source, source_reference=reference)
            if "randomness_controls" in capabilities
            else RandomnessResult(),
            input_reads=discover_inputs(source, source_reference=reference)
            if "input_reads" in capabilities
            else InputResult(),
        )
        return admit_result(result, request=request)
