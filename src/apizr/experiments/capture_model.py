"""Versioned in-process evidence; v1 script/notebook artifacts stay unchanged."""

from enum import Enum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from apizr.capabilities.types import logical_module
from apizr.contracts.distribution import Digest
from apizr.experiments.model import (
    EnvironmentEvidence,
    EvidenceOrigin,
    ExecutionIntent,
    ExperimentPlan,
    ExperimentRun,
    ExperimentValue,
    InputArtifact,
    Metric,
    N,
    Name,
    OutputArtifact,
    Parameter,
    RandomnessControl,
    RunDiagnostic,
    RunTiming,
    SourceIdentity,
    Text,
    ordered_evidence,
)
from apizr.experiments.values import FiniteValue


class CaptureMode(str, Enum):
    CLI_RUN = "cli_run"
    SDK_SESSION = "sdk_session"
    DECORATED_CALL = "decorated_call"
    JUPYTER_CELL = "jupyter_cell"
    UNKNOWN = "unknown"


class SourceEvidence(ExperimentValue):
    """A source identity is absent when no source bytes have been observed."""

    identity: SourceIdentity | None = None
    origin: Literal[EvidenceOrigin.RUNTIME, EvidenceOrigin.UNKNOWN] = (
        EvidenceOrigin.UNKNOWN
    )

    @model_validator(mode="after")
    def known_source(self) -> Self:
        if (self.origin == EvidenceOrigin.UNKNOWN) != (self.identity is None):
            raise ValueError("experiment_source_origin_value")
        return self


class FunctionBinding(ExperimentValue):
    module: Name | None = None
    qualified_name: Text | None = None
    definition_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")] | None = None
    source_digest: Digest | None = None
    origin: Literal[EvidenceOrigin.RUNTIME, EvidenceOrigin.UNKNOWN] = (
        EvidenceOrigin.UNKNOWN
    )

    @field_validator("module")
    @classmethod
    def module_name(cls, value: str | None) -> str | None:
        return logical_module(value) if value is not None else None

    @model_validator(mode="after")
    def known_function(self) -> Self:
        values = (
            self.module,
            self.qualified_name,
            self.definition_id,
            self.source_digest,
        )
        if self.origin == EvidenceOrigin.UNKNOWN:
            if any(value is not None for value in values):
                raise ValueError("experiment_unknown_function_has_value")
        elif self.module is None or self.qualified_name is None:
            raise ValueError("experiment_function_binding_incomplete")
        return self


class CellIdentity(ExperimentValue):
    cell_id: Name | None = None
    execution_count: Annotated[int, Field(ge=1, le=2**63 - 1)] | None = None
    source_digest: Digest | None = None
    origin: Literal[EvidenceOrigin.RUNTIME, EvidenceOrigin.UNKNOWN] = (
        EvidenceOrigin.UNKNOWN
    )

    @model_validator(mode="after")
    def known_cell(self) -> Self:
        values = (self.cell_id, self.execution_count, self.source_digest)
        if self.origin == EvidenceOrigin.UNKNOWN:
            if any(value is not None for value in values):
                raise ValueError("experiment_unknown_cell_has_value")
        elif all(value is None for value in values):
            raise ValueError("experiment_cell_identity_empty")
        return self


class CaptureIdentity(ExperimentValue):
    mode: CaptureMode
    producer: Name
    producer_version: Name
    function: FunctionBinding = FunctionBinding()
    cell: CellIdentity = CellIdentity()
    selected_parameters: Annotated[tuple[Name, ...], Field(max_length=256)] = ()

    @field_validator("selected_parameters")
    @classmethod
    def ordered_parameters(cls, names: tuple[str, ...]) -> tuple[str, ...]:
        return ordered_evidence(names, lambda name: name)

    @model_validator(mode="after")
    def applicable_bindings(self) -> Self:
        if self.mode == CaptureMode.DECORATED_CALL and (
            self.function.origin == EvidenceOrigin.UNKNOWN
        ):
            raise ValueError("experiment_decorated_call_function_unknown")
        if self.selected_parameters and self.function.origin == EvidenceOrigin.UNKNOWN:
            raise ValueError("experiment_call_parameters_function_unknown")
        if (
            self.mode == CaptureMode.JUPYTER_CELL
            and self.cell.origin == EvidenceOrigin.UNKNOWN
        ):
            raise ValueError("experiment_jupyter_cell_unknown")
        return self


class CallParameter(ExperimentValue):
    """Selected JSON or an explicit unknown value with its bounded type name."""

    name: Name
    value: FiniteValue
    value_type: Text | None = None
    origin: Literal[EvidenceOrigin.RUNTIME, EvidenceOrigin.UNKNOWN]

    @model_validator(mode="after")
    def unknown_value(self) -> Self:
        if self.origin == EvidenceOrigin.UNKNOWN and self.value is not None:
            raise ValueError("experiment_unknown_has_value")
        return self


class ExperimentPlanV2(ExperimentValue):
    schema_version: Literal["apizr.experiment-plan/v2"] = "apizr.experiment-plan/v2"
    subject: SourceEvidence
    execution: ExecutionIntent
    capture: CaptureIdentity
    inputs: Annotated[tuple[InputArtifact, ...], Field(max_length=256)] = ()
    parameters: Annotated[tuple[Parameter, ...], Field(max_length=256)] = ()
    randomness: Annotated[tuple[RandomnessControl, ...], Field(max_length=128)] = ()
    environment: EnvironmentEvidence | None = None

    @field_validator("inputs")
    @classmethod
    def ordered_inputs(
        cls, items: tuple[InputArtifact, ...]
    ) -> tuple[InputArtifact, ...]:
        return ExperimentPlan.ordered_named(items)

    @field_validator("parameters")
    @classmethod
    def ordered_parameters(cls, items: tuple[Parameter, ...]) -> tuple[Parameter, ...]:
        return ExperimentPlan.ordered_named(items)

    @field_validator("randomness")
    @classmethod
    def ordered_controls(
        cls, items: tuple[RandomnessControl, ...]
    ) -> tuple[RandomnessControl, ...]:
        return ExperimentPlan.ordered_controls(items)

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


class ExperimentRunV2(ExperimentValue):
    schema_version: Literal["apizr.experiment-run/v2"] = "apizr.experiment-run/v2"
    plan_digest: Digest
    subject: SourceEvidence
    capture: CaptureIdentity
    execution_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    call_parameters: Annotated[tuple[CallParameter, ...], Field(max_length=256)] = ()
    status: Literal["success", "failed", "cancelled"]
    observed_inputs: Annotated[tuple[InputArtifact, ...], Field(max_length=256)] = ()
    effective_parameters: Annotated[tuple[Parameter, ...], Field(max_length=256)] = ()
    randomness: Annotated[tuple[RandomnessControl, ...], Field(max_length=128)] = ()
    environment: EnvironmentEvidence | None = None
    metrics: Annotated[tuple[Metric, ...], Field(max_length=256)] = ()
    outputs: Annotated[tuple[OutputArtifact, ...], Field(max_length=256)] = ()
    timing: RunTiming | None = None
    diagnostics: Annotated[tuple[RunDiagnostic, ...], Field(max_length=32)] = ()

    @field_validator(
        "call_parameters",
        "observed_inputs",
        "effective_parameters",
        "metrics",
        "outputs",
    )
    @classmethod
    def ordered_named(cls, items: tuple[N, ...]) -> tuple[N, ...]:
        return ordered_evidence(items, lambda item: item.name)

    @field_validator("randomness")
    @classmethod
    def ordered_controls(
        cls, items: tuple[RandomnessControl, ...]
    ) -> tuple[RandomnessControl, ...]:
        return ExperimentRun.ordered_controls(items)

    @field_validator("diagnostics")
    @classmethod
    def ordered_diagnostics(
        cls, items: tuple[RunDiagnostic, ...]
    ) -> tuple[RunDiagnostic, ...]:
        return ExperimentRun.ordered_diagnostics(items)

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
        if (
            tuple(item.name for item in self.call_parameters)
            != self.capture.selected_parameters
        ):
            raise ValueError("experiment_call_parameter_selection_mismatch")
        return self


Plan = ExperimentPlan | ExperimentPlanV2
Run = ExperimentRun | ExperimentRunV2
