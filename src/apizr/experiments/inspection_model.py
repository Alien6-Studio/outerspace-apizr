"""Static inspection evidence and deterministic section states, separate from a Run."""

import json
from collections.abc import Callable
from enum import Enum
from typing import Annotated, Literal, Self, TypeVar, cast

from pydantic import BaseModel, BeforeValidator, Field, field_validator, model_validator

from apizr.capabilities.model import Diagnostic, Digest, Source
from apizr.experiments.environment import EnvironmentResult
from apizr.experiments.inputs import FingerprintPolicy, InputResult
from apizr.experiments.metrics import MetricDiscoveryResult
from apizr.experiments.model import EvidenceOrigin, ExperimentValue, Reference
from apizr.experiments.notebook_source import SourceLocation
from apizr.experiments.outputs import OutputDiscoveryResult
from apizr.experiments.parameters import ParameterDiscoveryResult
from apizr.experiments.randomness import RandomnessResult
from apizr.readiness import ReadinessReport, State, report_digest
from apizr.repository.model import CapabilityEntry
from apizr.repository_views.model import CapabilityFocus, ReadinessIdentity

M = TypeVar("M", bound=BaseModel)


def _checked(model: type[M]) -> Callable[[object], M]:
    # Enforce strict admission before older canonical models can coerce a value.
    # Existing instances also need revalidation, including unchecked model_copy.
    def validate(value: object) -> M:
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="json")
        try:
            raw = json.dumps(value, allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("inspection_canonical_value_invalid") from None
        return model.model_validate_json(raw, strict=True)

    return validate


class SectionState(str, Enum):
    CAPTURED = "captured"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    UNCONTROLLED = "uncontrolled"
    NOT_APPLICABLE = "not_applicable"


class CodeEvidence(ExperimentValue):
    reference: Reference
    source: Annotated[Source, BeforeValidator(_checked(Source))]
    ir_digest: Annotated[Digest, BeforeValidator(_checked(Digest))]
    readiness_digest: Annotated[Digest, BeforeValidator(_checked(Digest))]
    signal_digest: Annotated[Digest, BeforeValidator(_checked(Digest))]
    diagnostics: Annotated[
        tuple[Annotated[Diagnostic, BeforeValidator(_checked(Diagnostic))], ...],
        Field(max_length=4096),
    ] = ()

    @model_validator(mode="after")
    def bound(self) -> Self:
        if self.source.kind == "python" and self.signal_digest != self.source.digest:
            raise ValueError("inspection_signal_digest_mismatch")
        if any(d.source.module != self.source.module for d in self.diagnostics):
            raise ValueError("inspection_diagnostic_source_mismatch")
        return self


class RepositoryServing(ExperimentValue):
    identity: Annotated[ReadinessIdentity, BeforeValidator(_checked(ReadinessIdentity))]
    candidates: Annotated[
        tuple[
            Annotated[CapabilityFocus, BeforeValidator(_checked(CapabilityFocus))], ...
        ],
        Field(max_length=4096),
    ]


class ServingEvidence(ExperimentValue):
    readiness: Annotated[ReadinessReport, BeforeValidator(_checked(ReadinessReport))]
    capabilities: Annotated[
        tuple[
            Annotated[CapabilityEntry, BeforeValidator(_checked(CapabilityEntry))], ...
        ],
        Field(max_length=4096),
    ]
    repository: RepositoryServing | None = None

    @field_validator("capabilities")
    @classmethod
    def ordered(
        cls, values: tuple[CapabilityEntry, ...]
    ) -> tuple[CapabilityEntry, ...]:
        if len({c.id for c in values}) != len(values):
            raise ValueError("inspection_duplicate_capability")
        return tuple(sorted(values, key=lambda c: c.id))


class EvidenceLocation(ExperimentValue):
    """JSON pointer to retained evidence, with original notebook location if present."""

    evidence: Annotated[
        str,
        Field(
            pattern=r"^/(code/diagnostics|data/(artifacts|diagnostics)|parameters/(signals|diagnostics)|randomness/(controls|diagnostics)|metrics/signals|outputs/(signals|diagnostics)|serving/readiness/(assessments|structured_types))/[0-9]+$",
            max_length=128,
        ),
    ]
    location: SourceLocation


class InspectionStates(ExperimentValue):
    code: SectionState
    data: SectionState
    parameters: SectionState
    randomness: SectionState
    environment: SectionState
    metrics: SectionState
    outputs: SectionState
    serving: SectionState


class ExperimentInspection(ExperimentValue):
    schema_version: Literal["apizr.experiment-inspection/v1"] = (
        "apizr.experiment-inspection/v1"
    )
    execution: Literal["not_executed"] = "not_executed"
    fingerprint_policy: FingerprintPolicy
    code: CodeEvidence
    data: InputResult
    parameters: ParameterDiscoveryResult
    randomness: RandomnessResult
    environment: EnvironmentResult
    metrics: MetricDiscoveryResult
    outputs: OutputDiscoveryResult
    serving: ServingEvidence
    locations: Annotated[tuple[EvidenceLocation, ...], Field(max_length=8192)] = ()
    states: InspectionStates

    @field_validator("locations")
    @classmethod
    def ordered_locations(
        cls, values: tuple[EvidenceLocation, ...]
    ) -> tuple[EvidenceLocation, ...]:
        return tuple(
            sorted(
                set(values),
                key=lambda v: (v.evidence, v.location.line, v.location.column),
            )
        )

    def derived_states(self) -> InspectionStates:
        def static_state(
            records: tuple[object, ...], diagnostics: tuple[object, ...], complete: bool
        ) -> SectionState:
            if not records and not diagnostics:
                return SectionState.UNKNOWN
            return (
                SectionState.CAPTURED
                if records and not diagnostics and complete
                else SectionState.PARTIAL
            )

        random_state = static_state(
            self.randomness.controls,
            self.randomness.diagnostics,
            all(c.origin == EvidenceOrigin.STATIC for c in self.randomness.controls),
        )
        if any(
            d.code == "uncontrolled_randomness" for d in self.randomness.diagnostics
        ):
            random_state = SectionState.UNCONTROLLED
        return InspectionStates(
            code=SectionState.CAPTURED,
            data=static_state(
                self.data.artifacts,
                self.data.diagnostics,
                all(a.digest is not None for a in self.data.artifacts),
            ),
            parameters=static_state(
                self.parameters.signals, self.parameters.diagnostics, True
            ),
            randomness=random_state,
            environment=SectionState.PARTIAL
            if self.environment.evidence.artifacts
            or self.environment.diagnostics
            or self.randomness.relevant_distributions
            or self.metrics.relevant_distributions
            or self.outputs.relevant_distributions
            else SectionState.UNKNOWN,
            metrics=SectionState.PARTIAL
            if self.metrics.signals or self.metrics.diagnostics
            else SectionState.UNKNOWN,
            outputs=SectionState.PARTIAL
            if self.outputs.signals or self.outputs.diagnostics
            else SectionState.UNKNOWN,
            # Source-local readiness does not establish whole-project serving.
            serving=SectionState.PARTIAL
            if self.serving.readiness.assessments
            else SectionState.UNKNOWN,
        )

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.states != self.derived_states():
            raise ValueError("inspection_states_disagree")
        readiness = self.serving.readiness
        if (
            readiness.source != self.code.source
            or readiness.ir_digest != self.code.ir_digest
            or report_digest(readiness) != self.code.readiness_digest
        ):
            raise ValueError("inspection_readiness_identity_mismatch")
        assessments = {a.capability_id: a for a in readiness.assessments}
        entries = {c.id: c for c in self.serving.capabilities}
        if set(entries) != {a.capability_id for a in assessments.values() if a.in_ir}:
            raise ValueError("inspection_capability_membership_mismatch")
        for entry in entries.values():
            assessment = assessments[entry.id]
            if (
                entry.module != self.code.source.module
                or entry.source_path != self.code.reference
                or entry.source_digest != self.code.source.digest
                or entry.ir_digest != self.code.ir_digest
                or entry.readiness_digest != self.code.readiness_digest
                or entry.span != assessment.source
                or entry.readiness != assessment.state
                or entry.can_generate_interface != assessment.can_generate_interface
            ):
                raise ValueError("inspection_capability_identity_mismatch")
        repository = self.serving.repository
        if repository is not None:
            if tuple(c.capability_id for c in repository.candidates) != tuple(
                sorted(assessments)
            ):
                raise ValueError("inspection_repository_membership_mismatch")
            for candidate in repository.candidates:
                if (
                    candidate.module != self.code.source.module
                    or candidate.source_path != self.code.reference
                    or candidate.capability != entries.get(candidate.capability_id)
                    or candidate.local_readiness != assessments[candidate.capability_id]
                    or candidate.interface_eligible
                    != (
                        candidate.capability is not None
                        and candidate.selected_state == State.READY
                    )
                ):
                    raise ValueError("inspection_repository_identity_mismatch")
        if any(
            a.origin not in (EvidenceOrigin.STATIC, EvidenceOrigin.DECLARED)
            or a.content_origin not in (EvidenceOrigin.STATIC, EvidenceOrigin.UNKNOWN)
            for a in self.data.artifacts
        ):
            raise ValueError("inspection_runtime_data")
        # RandomnessResult itself rejects non-static/non-unknown controls.
        environment = self.environment.evidence
        if (
            environment.packages
            or any(
                value is not None and value.origin != EvidenceOrigin.UNKNOWN
                for value in (
                    environment.python_implementation,
                    environment.python_version,
                    environment.platform,
                    environment.architecture,
                )
            )
            or any(
                a.origin != EvidenceOrigin.STATIC
                or a.content_origin
                not in (EvidenceOrigin.STATIC, EvidenceOrigin.UNKNOWN)
                for a in environment.artifacts
            )
        ):
            raise ValueError("inspection_runtime_environment")
        # A location cannot point to unrelated, nonexistent or runtime evidence.
        for records in (
            self.data.diagnostics,
            self.parameters.signals,
            self.parameters.diagnostics,
            self.randomness.diagnostics,
            self.metrics.signals,
            self.metrics.diagnostics,
            self.outputs.signals,
            self.outputs.diagnostics,
        ):
            if any(
                record.source not in (None, self.code.reference) for record in records
            ):
                raise ValueError("inspection_signal_source_mismatch")
        for located in self.locations:
            value: object = self
            for component in located.evidence[1:].split("/"):
                if isinstance(value, tuple):
                    value = cast(tuple[object, ...], value)
                    index = int(component)
                    if index >= len(value):
                        raise ValueError("inspection_location_missing_record")
                    value = value[index]
                else:
                    value = getattr(value, component)
            if located.location.source != self.code.reference or (
                self.code.source.kind == "notebook"
            ) != (located.location.cell_index is not None):
                raise ValueError("inspection_location_source_mismatch")
            if located.evidence.startswith(
                (
                    "/parameters/",
                    "/metrics/",
                    "/outputs/",
                    "/data/diagnostics/",
                    "/randomness/diagnostics/",
                )
            ) and (getattr(value, "line", None), getattr(value, "column", None)) != (
                located.location.line,
                located.location.column,
            ):
                raise ValueError("inspection_location_position_mismatch")
        return self
