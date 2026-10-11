"""Pure intent derivation for explicit trusted whole-workload execution."""

import keyword
import re
from typing import Annotated, Self

from pydantic import AfterValidator, Field, field_validator, model_validator

from apizr.contracts.json import encode
from apizr.experiments.inspection_model import ExperimentInspection
from apizr.experiments.model import (
    EvidenceOrigin,
    ExecutionIntent,
    ExperimentPlan,
    ExperimentValue,
    Name,
    Parameter,
    SourceIdentity,
    ordered_evidence,
)
from apizr.experiments.outputs import OutputDeclaration


def _identifier(value: str) -> str:
    if not value.isidentifier() or keyword.iskeyword(value):
        raise ValueError("metric_binding_invalid")
    return value


Identifier = Annotated[Name, AfterValidator(_identifier)]


class MetricBinding(ExperimentValue):
    name: Name
    binding: Identifier


def parse_metric_binding(value: str) -> MetricBinding:
    try:
        name, separator, binding = value.partition("=")
        if not separator:
            raise ValueError
        return MetricBinding(name=name, binding=binding)
    except (ValueError, UnicodeError):
        raise ValueError("metric_binding_invalid") from None


class RunOptions(ExperimentValue):
    """Controls and required observations; never environment variable values."""

    timeout_ms: Annotated[int, Field(ge=1, le=3_600_000)] = 60_000
    inherit_environment: bool = False
    environment_names: Annotated[tuple[Name, ...], Field(max_length=128)] = ()
    metrics: Annotated[tuple[MetricBinding, ...], Field(max_length=256)] = ()
    outputs: Annotated[tuple[OutputDeclaration, ...], Field(max_length=256)] = ()
    max_output_bytes: Annotated[int, Field(ge=1, le=1024**4)] = 1024**3

    @field_validator("environment_names")
    @classmethod
    def names(cls, names: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n) for n in names):
            raise ValueError("environment_name_invalid")
        return tuple(sorted(set(names)))

    @field_validator("metrics")
    @classmethod
    def unique_metrics(
        cls, items: tuple[MetricBinding, ...]
    ) -> tuple[MetricBinding, ...]:
        return ordered_evidence(items, lambda item: item.name)

    @field_validator("outputs")
    @classmethod
    def unique_outputs(
        cls, items: tuple[OutputDeclaration, ...]
    ) -> tuple[OutputDeclaration, ...]:
        return ordered_evidence(items, lambda item: item.name)

    @model_validator(mode="after")
    def environment_mode(self) -> Self:
        if self.inherit_environment and self.environment_names:
            raise ValueError("environment_modes_conflict")
        return self


def derive_plan(
    inspection: ExperimentInspection, *, execution: RunOptions | None = None
) -> ExperimentPlan:
    """Promote only names whose static candidate values agree, with no execution.

    Unknown assignments are not evaluated. These are intended static candidates,
    not a claim about final bindings or about which values a workload consumes.
    """
    inspection = ExperimentInspection.model_validate(inspection)
    options = (
        RunOptions() if execution is None else RunOptions.model_validate(execution)
    )
    candidates: dict[str, dict[bytes, Parameter]] = {}
    for signal in inspection.parameters.signals:
        parameter = signal.parameter
        identity = encode(parameter.model_dump(mode="json"), 128 * 1024)
        candidates.setdefault(parameter.name, {})[identity] = parameter
    parameters = tuple(
        next(iter(values.values()))
        for values in candidates.values()
        if len(values) == 1
    )
    controls = {
        "timeout_ms": options.timeout_ms,
        "environment": "inherit" if options.inherit_environment else "clean",
        "environment_names": options.environment_names,
        "working_directory": "experiment-root",
        "filesystem": "host",
        "network": "host",
        "subprocess": "allowed",
        "interpreter": "current",
        "max_input_bytes": inspection.fingerprint_policy.max_file_bytes,
        "max_output_bytes": options.max_output_bytes,
        "required_metrics": tuple(m.model_dump(mode="json") for m in options.metrics),
        "required_outputs": tuple(o.model_dump(mode="json") for o in options.outputs),
        "observation_policy": "static-bindings-and-boundary-snapshots/v1",
    }
    source = inspection.code.source
    return ExperimentPlan(
        subject=SourceIdentity(
            kind=source.kind,
            reference=inspection.code.reference,
            digest=source.digest.value,
            executable_digest=(
                source.transformed_digest.value
                if source.transformed_digest is not None
                else source.digest.value
            ),
            module=source.module,
        ),
        execution=ExecutionIntent(
            kind="trusted-local-process",
            controls=tuple(
                Parameter.model_validate(
                    {"name": name, "value": value, "origin": EvidenceOrigin.DECLARED}
                )
                for name, value in controls.items()
            ),
        ),
        inputs=inspection.data.artifacts,
        parameters=parameters,
        randomness=inspection.randomness.controls,
        environment=inspection.environment.evidence,
    )
