"""Static provider and in-process SDK adapter contracts, without discovery."""

from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, field_validator, model_validator

from apizr.contracts.distribution import Digest
from apizr.experiments.inputs import InputResult
from apizr.experiments.metrics import MetricDiscoveryResult
from apizr.experiments.model import EvidenceOrigin, ExperimentValue, Name, Reference
from apizr.experiments.outputs import OutputDiscoveryResult
from apizr.experiments.provider_source import SourceView
from apizr.experiments.randomness import RandomnessResult

IdentityName = Annotated[Name, Field(pattern=r"^[a-z][a-z0-9_.-]*$")]
StaticCapability = Literal[
    "metric_signals", "output_candidates", "randomness_controls", "input_reads"
]
SDKCapability = Literal["parameter", "metric", "input", "artifact"]


class ProducerIdentity(ExperimentValue):
    name: IdentityName
    version: Name


class ProviderLimits(ExperimentValue):
    """Declarative ceilings, always at or below core hard bounds."""

    max_source_bytes: Annotated[int, Field(ge=1, le=1024 * 1024)] = 1024 * 1024
    max_ast_nodes: Annotated[int, Field(ge=1, le=100_000)] = 100_000
    max_ast_depth: Annotated[int, Field(ge=1, le=128)] = 128
    max_evidence: Annotated[int, Field(ge=1, le=256)] = 256
    max_diagnostics: Annotated[int, Field(ge=1, le=512)] = 512
    max_result_bytes: Annotated[int, Field(ge=1, le=1024 * 1024)] = 1024 * 1024


class ProviderDescriptor(ExperimentValue):
    schema_version: Literal["apizr.scientific-provider/v1"] = (
        "apizr.scientific-provider/v1"
    )
    identity: ProducerIdentity
    capabilities: Annotated[
        tuple[StaticCapability, ...], Field(min_length=1, max_length=4)
    ]
    limits: ProviderLimits = ProviderLimits()
    observation: Literal["static-only"] = "static-only"

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(
        cls, values: tuple[StaticCapability, ...]
    ) -> tuple[StaticCapability, ...]:
        if len(set(values)) != len(values):
            raise ValueError("provider_capability_duplicate")
        return tuple(sorted(values))


class ProviderRequest(ExperimentValue):
    schema_version: Literal["apizr.scientific-request/v1"] = (
        "apizr.scientific-request/v1"
    )
    provider: ProviderDescriptor
    source: SourceView

    @model_validator(mode="after")
    def lowered_bounds(self) -> Self:
        limits = self.provider.limits
        self.source.tree(
            max_bytes=limits.max_source_bytes,
            max_nodes=limits.max_ast_nodes,
            max_depth=limits.max_ast_depth,
        )
        return self


class ProviderLocation(ExperimentValue):
    source: Reference
    line: Annotated[int, Field(ge=1, le=1024 * 1024)] | None = None
    column: Annotated[int, Field(ge=0, le=1024 * 1024)] | None = None

    @model_validator(mode="after")
    def paired_position(self) -> Self:
        if (self.line is None) != (self.column is None):
            raise ValueError("provider_location_incomplete")
        return self


class ProviderDiagnostic(ExperimentValue):
    code: Literal[
        "provider_unavailable",
        "provider_disabled",
        "provider_incompatible",
        "provider_failed",
        "provider_result_invalid",
        "provider_limit",
        "provider_unsupported",
    ]
    location: ProviderLocation
    capability: StaticCapability | None = None
    origin: Literal[EvidenceOrigin.UNKNOWN] = EvidenceOrigin.UNKNOWN


class ProviderResult(ExperimentValue):
    """Untrusted candidate input, reusing canonical evidence types exclusively."""

    schema_version: Literal["apizr.scientific-result/v1"] = "apizr.scientific-result/v1"
    identity: ProducerIdentity
    source: Reference
    source_digest: Digest
    metric_signals: MetricDiscoveryResult = MetricDiscoveryResult()
    output_candidates: OutputDiscoveryResult = OutputDiscoveryResult()
    randomness_controls: RandomnessResult = RandomnessResult()
    input_reads: InputResult = InputResult()
    diagnostics: Annotated[tuple[ProviderDiagnostic, ...], Field(max_length=512)] = ()

    @model_validator(mode="after")
    def static_evidence_only(self) -> Self:
        for item in self.input_reads.artifacts:
            if (
                item.origin not in {EvidenceOrigin.STATIC, EvidenceOrigin.UNKNOWN}
                or item.digest is not None
                or item.size is not None
                or item.content_origin not in {None, EvidenceOrigin.UNKNOWN}
            ):
                raise ValueError("provider_input_not_static")
        return self


class StaticProvider(Protocol):
    """Explicitly chosen trusted code; never an automatic import/entrypoint loader."""

    @property
    def descriptor(self) -> ProviderDescriptor: ...

    def recognize(self, request: ProviderRequest) -> ProviderResult: ...


class SDKAdapterDescriptor(ExperimentValue):
    schema_version: Literal["apizr.scientific-adapter/v1"] = (
        "apizr.scientific-adapter/v1"
    )
    identity: ProducerIdentity
    capabilities: Annotated[
        tuple[SDKCapability, ...], Field(min_length=1, max_length=4)
    ]
    observation: Literal["explicit-in-process-values"] = "explicit-in-process-values"

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(
        cls, values: tuple[SDKCapability, ...]
    ) -> tuple[SDKCapability, ...]:
        if len(set(values)) != len(values):
            raise ValueError("adapter_capability_duplicate")
        return tuple(sorted(values))


class SDKReporter(Protocol):
    """Only bounded logging, with no store, root, Run or finalize authority."""

    def log_parameter(self, name: str, value: object) -> None: ...

    def log_metric(
        self, name: str, value: object, *, unit: str | None = None
    ) -> None: ...

    def log_input(
        self, name: str, reference: str | None = None, *, uri: str | None = None
    ) -> None: ...

    def log_artifact(
        self, name: str, reference: str, *, media_type: str | None = None
    ) -> None: ...


class SDKAdapter(Protocol):
    @property
    def descriptor(self) -> SDKAdapterDescriptor: ...

    def observe(self, value: object, *, reporter: SDKReporter) -> None:
        """Observe an explicitly supplied object in its existing scientific process."""
        ...
