"""Experiment intent and observed evidence; no capture or execution machinery."""

import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Literal, Protocol, Self, TypeVar

from pydantic import (
    AfterValidator,
    AwareDatetime,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from apizr.capabilities.types import ValueModel, logical_module
from apizr.contracts.distribution import Digest, canonical_name
from apizr.experiments.values import FiniteValue


def _text(value: str) -> str:
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("experiment_text_control_character")
    value.encode("utf-8")
    return value


Name = Annotated[str, Field(min_length=1, max_length=128), AfterValidator(_text)]
Text = Annotated[str, Field(min_length=1, max_length=256), AfterValidator(_text)]
Size = Annotated[int, Field(ge=0, le=2**63 - 1)]


class _Named(Protocol):
    @property
    def name(self) -> str: ...


T = TypeVar("T")
N = TypeVar("N", bound=_Named)


def ordered_evidence(
    items: tuple[T, ...], key: Callable[[T], str | tuple[str, str]]
) -> tuple[T, ...]:
    keys = [key(item) for item in items]
    if len(keys) != len(set(keys)):
        raise ValueError("experiment_duplicate_identity")
    return tuple(sorted(items, key=key))


def _reference(value: str) -> str:
    _text(value)
    if (
        any(part in ("", ".", "..") for part in value.split("/"))
        or any(char in value for char in ("\\", ":"))
        or value.startswith("~")
    ):
        raise ValueError("experiment_reference_not_project_relative")
    return value


Reference = Annotated[
    str, Field(min_length=1, max_length=1024), AfterValidator(_reference)
]


def _uri(value: str) -> str:
    # Deliberately narrower than general URL parsing: no credentials, percent
    # escapes, query, fragment, port, Unicode authority or local-file scheme.
    if not re.fullmatch(
        r"(?:https|s3|gs)://[a-z0-9]+(?:[.-][a-z0-9]+)*(?:/[A-Za-z0-9._~-]+)*",
        value,
    ) or any(part in (".", "..") for part in value.split("/")[3:]):
        raise ValueError("experiment_uri_unsupported")
    return value


RemoteURI = Annotated[str, Field(max_length=1024), AfterValidator(_uri)]
FormatHint = Literal["csv", "parquet", "numpy", "joblib"]


class EvidenceOrigin(str, Enum):
    DECLARED = "declared"
    STATIC = "static"
    RUNTIME = "runtime"
    UNKNOWN = "unknown"


class ExperimentValue(ValueModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


class SourceIdentity(ExperimentValue):
    kind: Literal["python", "notebook"]
    reference: Reference
    digest: Digest
    executable_digest: Digest | None = None
    module: Annotated[Name, AfterValidator(logical_module)] | None = None
    capability_id: (
        Annotated[
            str,
            Field(min_length=1, max_length=512, pattern=r"^[^\s/\\]+$"),
            AfterValidator(_text),
        ]
        | None
    ) = None


class InputArtifact(ExperimentValue):
    name: Name
    reference: Reference | None = None
    digest: Digest | None = None
    size: Size | None = None
    origin: EvidenceOrigin
    content_origin: EvidenceOrigin | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    format_hint: FormatHint | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    uri: RemoteURI | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def unknown_content(self) -> Self:
        if self.reference is not None and self.uri is not None:
            raise ValueError("experiment_input_reference_conflict")
        has_content = self.digest is not None or self.size is not None
        if self.content_origin is not None and (
            (self.content_origin == EvidenceOrigin.UNKNOWN) == has_content
        ):
            raise ValueError("experiment_input_content_origin_value")
        if self.origin == EvidenceOrigin.UNKNOWN and (
            self.digest is not None or self.size is not None
        ):
            raise ValueError("experiment_unknown_content_has_value")
        return self

    def origins(self) -> Iterable[EvidenceOrigin]:
        yield self.origin
        if self.content_origin is not None:
            yield self.content_origin


class Parameter(ExperimentValue):
    name: Name
    value: FiniteValue
    origin: EvidenceOrigin

    @model_validator(mode="after")
    def unknown_value(self) -> Self:
        if self.origin == EvidenceOrigin.UNKNOWN and self.value is not None:
            raise ValueError("experiment_unknown_has_value")
        return self


class RandomnessControl(Parameter):
    provider: Name


class EnvironmentValue(ExperimentValue):
    value: Text | None
    origin: EvidenceOrigin

    @model_validator(mode="after")
    def known_value(self) -> Self:
        if (self.origin == EvidenceOrigin.UNKNOWN) != (self.value is None):
            raise ValueError("experiment_environment_origin_value")
        return self


class PackageEvidence(ExperimentValue):
    name: Annotated[Name, AfterValidator(canonical_name)]
    version: Name | None
    origin: EvidenceOrigin

    @model_validator(mode="after")
    def known_version(self) -> Self:
        if (self.origin == EvidenceOrigin.UNKNOWN) != (self.version is None):
            raise ValueError("experiment_package_origin_version")
        return self


class EnvironmentEvidence(ExperimentValue):
    python_implementation: EnvironmentValue | None = None
    python_version: EnvironmentValue | None = None
    platform: EnvironmentValue | None = None
    architecture: EnvironmentValue | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    packages: Annotated[tuple[PackageEvidence, ...], Field(max_length=4096)] = ()
    artifacts: Annotated[tuple[InputArtifact, ...], Field(max_length=64)] = ()

    @field_validator("packages", "artifacts")
    @classmethod
    def ordered_inventory(cls, items: tuple[N, ...]) -> tuple[N, ...]:
        return ordered_evidence(items, lambda item: item.name)

    def origins(self) -> Iterable[EvidenceOrigin]:
        for value in (
            self.python_implementation,
            self.python_version,
            self.platform,
            self.architecture,
        ):
            if value is not None:
                yield value.origin
        for record in self.packages:
            yield record.origin
        for artifact in self.artifacts:
            yield from artifact.origins()


class ExecutionIntent(ExperimentValue):
    kind: Name
    policy_digest: Digest | None = None
    controls: Annotated[tuple[Parameter, ...], Field(max_length=128)] = ()

    @field_validator("controls")
    @classmethod
    def declared_controls(cls, items: tuple[Parameter, ...]) -> tuple[Parameter, ...]:
        if any(item.origin != EvidenceOrigin.DECLARED for item in items):
            raise ValueError("experiment_execution_control_not_declared")
        return ordered_evidence(items, lambda item: item.name)


class Metric(ExperimentValue):
    name: Name
    value: (
        Annotated[int, Field(ge=-(2**63), le=2**63 - 1)]
        | Annotated[float, Field(allow_inf_nan=False)]
    )
    unit: (
        Annotated[str, Field(min_length=1, max_length=64), AfterValidator(_text)] | None
    ) = None
    origin: Literal[EvidenceOrigin.RUNTIME]

    @field_validator("value", mode="before")
    @classmethod
    def bounded_integer(cls, value: object) -> object:
        if type(value) is int and not -(2**63) <= value < 2**63:
            raise ValueError("experiment_metric_integer_range")
        return value


class OutputArtifact(ExperimentValue):
    name: Name
    digest: Digest
    size: Size | None = None
    media_type: Name | None = None
    origin: Literal[EvidenceOrigin.RUNTIME]


class RunDiagnostic(ExperimentValue):
    code: Annotated[
        str, Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_.-]*$")
    ]
    origin: Literal[EvidenceOrigin.RUNTIME]


class RunTiming(ExperimentValue):
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None
    duration_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    origin: Literal[EvidenceOrigin.RUNTIME]

    @field_validator("started_at", "ended_at")
    @classmethod
    def utc_time(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode="after")
    def observed_interval(self) -> Self:
        if (
            self.started_at is None
            and self.ended_at is None
            and self.duration_seconds is None
        ):
            raise ValueError("experiment_timing_empty")
        if (
            self.started_at is not None
            and self.ended_at is not None
            and self.ended_at < self.started_at
        ):
            raise ValueError("experiment_timing_reversed")
        return self


class ExperimentPlan(ExperimentValue):
    schema_version: Literal["apizr.experiment-plan/v1"] = "apizr.experiment-plan/v1"
    subject: SourceIdentity
    execution: ExecutionIntent
    inputs: Annotated[tuple[InputArtifact, ...], Field(max_length=256)] = ()
    parameters: Annotated[tuple[Parameter, ...], Field(max_length=256)] = ()
    randomness: Annotated[tuple[RandomnessControl, ...], Field(max_length=128)] = ()
    environment: EnvironmentEvidence | None = None

    @field_validator("inputs", "parameters")
    @classmethod
    def ordered_named(cls, items: tuple[N, ...]) -> tuple[N, ...]:
        return ordered_evidence(items, lambda item: item.name)

    @field_validator("randomness")
    @classmethod
    def ordered_controls(
        cls, items: tuple[RandomnessControl, ...]
    ) -> tuple[RandomnessControl, ...]:
        return ordered_evidence(items, lambda item: (item.provider, item.name))

    @model_validator(mode="after")
    def intended_evidence(self) -> Self:
        origins = [
            item.origin for item in (*self.inputs, *self.parameters, *self.randomness)
        ]
        origins.extend(
            item.content_origin
            for item in self.inputs
            if item.content_origin is not None
        )
        if self.environment is not None:
            origins.extend(self.environment.origins())
        if EvidenceOrigin.RUNTIME in origins:
            raise ValueError("experiment_plan_contains_runtime_observation")
        return self


class ExperimentRun(ExperimentValue):
    schema_version: Literal["apizr.experiment-run/v1"] = "apizr.experiment-run/v1"
    plan_digest: Digest
    subject: SourceIdentity
    status: Literal["success", "failed", "cancelled"]
    observed_inputs: Annotated[tuple[InputArtifact, ...], Field(max_length=256)] = ()
    effective_parameters: Annotated[tuple[Parameter, ...], Field(max_length=256)] = ()
    randomness: Annotated[tuple[RandomnessControl, ...], Field(max_length=128)] = ()
    environment: EnvironmentEvidence | None = None
    metrics: Annotated[tuple[Metric, ...], Field(max_length=256)] = ()
    outputs: Annotated[tuple[OutputArtifact, ...], Field(max_length=256)] = ()
    timing: RunTiming | None = None
    diagnostics: Annotated[tuple[RunDiagnostic, ...], Field(max_length=32)] = ()

    @field_validator("observed_inputs", "effective_parameters", "metrics", "outputs")
    @classmethod
    def ordered_named(cls, items: tuple[N, ...]) -> tuple[N, ...]:
        return ordered_evidence(items, lambda item: item.name)

    @field_validator("randomness")
    @classmethod
    def ordered_controls(
        cls, items: tuple[RandomnessControl, ...]
    ) -> tuple[RandomnessControl, ...]:
        return ordered_evidence(items, lambda item: (item.provider, item.name))

    @field_validator("diagnostics")
    @classmethod
    def ordered_diagnostics(
        cls, items: tuple[RunDiagnostic, ...]
    ) -> tuple[RunDiagnostic, ...]:
        return ordered_evidence(items, lambda item: item.code)

    @model_validator(mode="after")
    def observed_evidence(self) -> Self:
        origins = [
            item.origin
            for item in (
                *self.observed_inputs,
                *self.effective_parameters,
                *self.randomness,
            )
        ]
        origins.extend(
            item.content_origin
            for item in self.observed_inputs
            if item.content_origin is not None
        )
        if self.environment is not None:
            origins.extend(self.environment.origins())
        if any(
            origin not in {EvidenceOrigin.RUNTIME, EvidenceOrigin.UNKNOWN}
            for origin in origins
        ):
            raise ValueError("experiment_run_contains_unobserved_evidence")
        if self.status == "success" and self.diagnostics:
            raise ValueError("experiment_success_has_failure_diagnostics")
        return self
