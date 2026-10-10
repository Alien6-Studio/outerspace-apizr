"""Pure, directional comparison of validated, immutable recorded evidence.

Selection compares Plan intent; content compares Run observations. Missing
observations never inherit intent. Counts are comparison facets, not causes or
scores; exact Plan identity and timing are context, not counted facets.
"""

from collections.abc import Callable, Iterable
from enum import Enum
from math import isfinite
from typing import Annotated, Literal, TypeVar

from pydantic import Field

from apizr.contracts.distribution import Digest
from apizr.contracts.json import encode
from apizr.experiments.model import (
    EnvironmentEvidence,
    EnvironmentValue,
    EvidenceOrigin,
    ExperimentValue,
    InputArtifact,
    Metric,
    Name,
    OutputArtifact,
    PackageEvidence,
    Parameter,
    RandomnessControl,
    SourceIdentity,
)
from apizr.experiments.store import RunRecord

MAX_DIFF_BYTES = 32 * 1024 * 1024


class ChangeState(str, Enum):
    SAME = "same"
    CHANGED = "changed"
    ADDED = "added"
    REMOVED = "removed"
    UNKNOWN = "unknown"


class SourceChange(ExperimentValue):
    a: SourceIdentity
    b: SourceIdentity
    state: ChangeState
    kind: ChangeState
    reference: ChangeState
    digest: ChangeState
    executable_digest: ChangeState
    module: ChangeState
    capability_id: ChangeState


class InputChange(ExperimentValue):
    name: Name
    planned_a: InputArtifact | None
    observed_a: InputArtifact | None
    planned_b: InputArtifact | None
    observed_b: InputArtifact | None
    selection_state: ChangeState
    reference_state: ChangeState
    content_state: ChangeState


class ParameterChange(ExperimentValue):
    name: Name
    planned_a: Parameter | None
    observed_a: Parameter | None
    planned_b: Parameter | None
    observed_b: Parameter | None
    planned_state: ChangeState
    observed_state: ChangeState
    observed_membership: ChangeState


class RandomnessChange(ExperimentValue):
    provider: Name
    name: Name
    planned_a: RandomnessControl | None
    observed_a: RandomnessControl | None
    planned_b: RandomnessControl | None
    observed_b: RandomnessControl | None
    planned_state: ChangeState
    observed_state: ChangeState


class EnvironmentScalarChange(ExperimentValue):
    a: EnvironmentValue | None
    b: EnvironmentValue | None
    state: ChangeState


class PackageChange(ExperimentValue):
    name: Name
    a: PackageEvidence | None
    b: PackageEvidence | None
    state: ChangeState


class EnvironmentArtifactChange(ExperimentValue):
    name: Name
    a: InputArtifact | None
    b: InputArtifact | None
    state: ChangeState


class EnvironmentChange(ExperimentValue):
    python_implementation: EnvironmentScalarChange
    python_version: EnvironmentScalarChange
    platform: EnvironmentScalarChange
    architecture: EnvironmentScalarChange
    packages: Annotated[tuple[PackageChange, ...], Field(max_length=8192)]
    artifacts: Annotated[tuple[EnvironmentArtifactChange, ...], Field(max_length=128)]


class MetricChange(ExperimentValue):
    name: Name
    a: Metric | None
    b: Metric | None
    state: ChangeState
    delta: int | float | None = Field(default=None, exclude_if=lambda v: v is None)


class OutputChange(ExperimentValue):
    name: Name
    a: OutputArtifact | None
    b: OutputArtifact | None
    state: ChangeState
    content_state: ChangeState


class StatusChange(ExperimentValue):
    a: Literal["success", "failed", "cancelled"]
    b: Literal["success", "failed", "cancelled"]
    state: ChangeState


Count = Annotated[int, Field(ge=0, le=32768)]


class DifferenceCounts(ExperimentValue):
    changed: Count
    added: Count
    removed: Count
    unknown: Count


class ExperimentDiff(ExperimentValue):
    schema_version: Literal["apizr.experiment-diff/v1"] = "apizr.experiment-diff/v1"
    run_a_digest: Digest
    run_b_digest: Digest
    plan_a_digest: Digest
    plan_b_digest: Digest
    plan_state: ChangeState
    source: SourceChange
    serving: ChangeState
    data: Annotated[tuple[InputChange, ...], Field(max_length=1024)]
    parameters: Annotated[tuple[ParameterChange, ...], Field(max_length=1024)]
    randomness: Annotated[tuple[RandomnessChange, ...], Field(max_length=512)]
    planned_environment: EnvironmentChange
    observed_environment: EnvironmentChange
    status: StatusChange
    metrics: Annotated[tuple[MetricChange, ...], Field(max_length=512)]
    outputs: Annotated[tuple[OutputChange, ...], Field(max_length=512)]
    material_counts: DifferenceCounts
    result_counts: DifferenceCounts


def _exact(a: object, b: object) -> ChangeState:
    return ChangeState.SAME if a == b else ChangeState.CHANGED


def _known(a: object, b: object) -> ChangeState:
    if a is None or b is None:
        return ChangeState.UNKNOWN
    return _exact(a, b)


def _membership(a: object, b: object) -> ChangeState:
    if a is None:
        return ChangeState.UNKNOWN if b is None else ChangeState.ADDED
    return ChangeState.REMOVED if b is None else ChangeState.SAME


def _canonical(value: ExperimentValue) -> bytes:
    return encode(value.model_dump(mode="json"), MAX_DIFF_BYTES)


def _evidence(a: ExperimentValue | None, b: ExperimentValue | None) -> ChangeState:
    if a is None or b is None:
        return _membership(a, b)
    return _exact(_canonical(a), _canonical(b))


def _parameter(a: Parameter | None, b: Parameter | None) -> ChangeState:
    if a is None or b is None:
        return _membership(a, b)
    if EvidenceOrigin.UNKNOWN in (a.origin, b.origin):
        return ChangeState.UNKNOWN
    return _evidence(a, b)


def _content(a: InputArtifact | None, b: InputArtifact | None) -> ChangeState:
    return _known(a.digest if a else None, b.digest if b else None)


T = TypeVar("T", bound=ExperimentValue)
K = TypeVar("K", str, tuple[str, str])


def _joined(
    key: Callable[[T], K], *groups: tuple[T, ...]
) -> Iterable[tuple[K, tuple[T | None, ...]]]:
    indexes = [{key(item): item for item in group} for group in groups]
    for name in sorted({name for index in indexes for name in index}):
        yield name, tuple(index.get(name) for index in indexes)


def _environment(
    a: EnvironmentEvidence | None, b: EnvironmentEvidence | None
) -> EnvironmentChange:
    a, b = a or EnvironmentEvidence(), b or EnvironmentEvidence()

    def scalar(
        x: EnvironmentValue | None, y: EnvironmentValue | None
    ) -> EnvironmentScalarChange:
        state = _known(x.value if x else None, y.value if y else None)
        return EnvironmentScalarChange(a=x, b=y, state=state)

    packages = tuple(
        PackageChange(
            name=name,
            a=x,
            b=y,
            state=(
                _membership(x, y)
                if x is None or y is None
                else ChangeState.UNKNOWN
                if x.version is None or y.version is None
                else _evidence(x, y)
            ),
        )
        for name, (x, y) in _joined(lambda p: p.name, a.packages, b.packages)
    )
    artifacts = tuple(
        EnvironmentArtifactChange(
            name=name,
            a=x,
            b=y,
            state=(
                _membership(x, y)
                if x is None or y is None
                else ChangeState.UNKNOWN
                if _content(x, y) == ChangeState.UNKNOWN
                else _evidence(x, y)
            ),
        )
        for name, (x, y) in _joined(lambda p: p.name, a.artifacts, b.artifacts)
    )
    return EnvironmentChange(
        python_implementation=scalar(a.python_implementation, b.python_implementation),
        python_version=scalar(a.python_version, b.python_version),
        platform=scalar(a.platform, b.platform),
        architecture=scalar(a.architecture, b.architecture),
        packages=packages,
        artifacts=artifacts,
    )


def _metric(name: str, a: Metric | None, b: Metric | None) -> MetricChange:
    delta = None
    if a is not None and b is not None and a.unit == b.unit:
        x, y = a.value, b.value
        # Exact types exclude bool (a subclass of int). The narrowing below is
        # explicit for type checkers; it adds no coercion to the stored values.
        if type(x) in (int, float) and type(y) in (int, float):
            assert isinstance(x, (int, float)) and isinstance(y, (int, float))
            difference = y - x
            if isfinite(difference):
                delta = difference
    return MetricChange(name=name, a=a, b=b, state=_evidence(a, b), delta=delta)


def _environment_states(value: EnvironmentChange) -> tuple[ChangeState, ...]:
    return (
        value.python_implementation.state,
        value.python_version.state,
        value.platform.state,
        value.architecture.state,
        *(item.state for item in value.packages),
        *(item.state for item in value.artifacts),
    )


def _counts(states: tuple[ChangeState, ...]) -> DifferenceCounts:
    return DifferenceCounts(
        changed=states.count(ChangeState.CHANGED),
        added=states.count(ChangeState.ADDED),
        removed=states.count(ChangeState.REMOVED),
        unknown=states.count(ChangeState.UNKNOWN),
    )


def compare_runs(a: RunRecord, b: RunRecord) -> ExperimentDiff:
    """Revalidate exact Run/Plan bindings, then compare A → B with zero I/O."""
    a = RunRecord.model_validate(a)
    b = RunRecord.model_validate(b)
    x, y = a.run.subject, b.run.subject
    serving = _evidence_identity(x.capability_id, y.capability_id)
    source = SourceChange(
        a=x,
        b=y,
        state=_evidence(x, y),
        kind=_exact(x.kind, y.kind),
        reference=_exact(x.reference, y.reference),
        digest=_exact(x.digest, y.digest),
        executable_digest=_known(x.executable_digest, y.executable_digest),
        module=_known(x.module, y.module),
        capability_id=serving,
    )
    data = tuple(
        InputChange(
            name=name,
            planned_a=pa,
            observed_a=oa,
            planned_b=pb,
            observed_b=ob,
            selection_state=_evidence(pa, pb),
            reference_state=_known(
                (pa.reference or pa.uri) if pa else None,
                (pb.reference or pb.uri) if pb else None,
            ),
            content_state=_content(oa, ob),
        )
        for name, (pa, oa, pb, ob) in _joined(
            lambda p: p.name,
            a.plan.inputs,
            a.run.observed_inputs,
            b.plan.inputs,
            b.run.observed_inputs,
        )
    )
    parameters = tuple(
        ParameterChange(
            name=name,
            planned_a=pa,
            observed_a=oa,
            planned_b=pb,
            observed_b=ob,
            planned_state=_parameter(pa, pb),
            observed_state=ChangeState.UNKNOWN
            if oa is None or ob is None
            else _parameter(oa, ob),
            observed_membership=_membership(oa, ob),
        )
        for name, (pa, oa, pb, ob) in _joined(
            lambda p: p.name,
            a.plan.parameters,
            a.run.effective_parameters,
            b.plan.parameters,
            b.run.effective_parameters,
        )
    )
    randomness = tuple(
        RandomnessChange(
            provider=key[0],
            name=key[1],
            planned_a=pa,
            observed_a=oa,
            planned_b=pb,
            observed_b=ob,
            planned_state=_parameter(pa, pb),
            observed_state=_parameter(oa, ob),
        )
        for key, (pa, oa, pb, ob) in _joined(
            lambda p: (p.provider, p.name),
            a.plan.randomness,
            a.run.randomness,
            b.plan.randomness,
            b.run.randomness,
        )
    )
    planned_environment = _environment(a.plan.environment, b.plan.environment)
    observed_environment = _environment(a.run.environment, b.run.environment)
    metrics = tuple(
        _metric(name, x, y)
        for name, (x, y) in _joined(lambda p: p.name, a.run.metrics, b.run.metrics)
    )
    outputs = tuple(
        OutputChange(
            name=name,
            a=x,
            b=y,
            state=_evidence(x, y),
            content_state=_known(x.digest if x else None, y.digest if y else None),
        )
        for name, (x, y) in _joined(lambda p: p.name, a.run.outputs, b.run.outputs)
    )
    status = StatusChange(
        a=a.run.status, b=b.run.status, state=_exact(a.run.status, b.run.status)
    )
    material = (
        source.state,
        serving,
        *(s for item in data for s in (item.selection_state, item.content_state)),
        *(s for item in parameters for s in (item.planned_state, item.observed_state)),
        *(s for item in randomness for s in (item.planned_state, item.observed_state)),
        *_environment_states(planned_environment),
        *_environment_states(observed_environment),
    )
    result = ExperimentDiff(
        run_a_digest=a.run_digest,
        run_b_digest=b.run_digest,
        plan_a_digest=a.plan_digest,
        plan_b_digest=b.plan_digest,
        plan_state=_exact(a.plan_digest, b.plan_digest),
        source=source,
        serving=serving,
        data=data,
        parameters=parameters,
        randomness=randomness,
        planned_environment=planned_environment,
        observed_environment=observed_environment,
        status=status,
        metrics=metrics,
        outputs=outputs,
        material_counts=_counts(material),
        result_counts=_counts(
            (status.state, *(m.state for m in metrics), *(o.state for o in outputs))
        ),
    )
    diff_bytes(result)  # Bound the derived view even when each input is bounded.
    return result


def _evidence_identity(a: str | None, b: str | None) -> ChangeState:
    return _membership(a, b) if a is None or b is None else _exact(a, b)


def diff_bytes(value: ExperimentDiff) -> bytes:
    """Canonical UTF-8 JSON with a final newline; no separate diff identity."""
    return encode(
        ExperimentDiff.model_validate(value).model_dump(mode="json"), MAX_DIFF_BYTES
    )
