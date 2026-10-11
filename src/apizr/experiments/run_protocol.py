"""Bounded private workload messages; separate from capability invocation contracts."""

import base64
from hashlib import sha256
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from apizr.contracts.distribution import Digest
from apizr.experiments.inputs import FingerprintPolicy
from apizr.experiments.model import (
    EnvironmentEvidence,
    ExperimentValue,
    InputArtifact,
    Metric,
    Name,
    Parameter,
    SourceIdentity,
)
from apizr.experiments.planning import MetricBinding

MAX_REQUEST_BYTES = 32 * 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_CAPTURE_BYTES = 1024 * 1024


class WorkloadRequest(ExperimentValue):
    schema_version: Literal["apizr.experiment-worker/v1"] = "apizr.experiment-worker/v1"
    subject: SourceIdentity
    plan_digest: Digest
    original: Annotated[str, Field(max_length=24 * 1024 * 1024)]
    executable: Annotated[str, Field(max_length=2 * 1024 * 1024)]
    parameters: Annotated[tuple[Name, ...], Field(max_length=256)] = ()
    automatic_metrics: Annotated[tuple[MetricBinding, ...], Field(max_length=256)] = ()
    required_metrics: Annotated[tuple[MetricBinding, ...], Field(max_length=256)] = ()
    distributions: Annotated[tuple[Name, ...], Field(max_length=64)] = ()
    inputs: Annotated[tuple[InputArtifact, ...], Field(max_length=256)] = ()
    fingerprint_policy: FingerprintPolicy = FingerprintPolicy()

    def executable_bytes(self) -> bytes:
        original = base64.b64decode(self.original, validate=True)
        executable = base64.b64decode(self.executable, validate=True)
        if (
            len(original) > (1024**2 if self.subject.kind == "python" else 16 * 1024**2)
            or len(executable) > 1024**2
            or sha256(original).hexdigest() != self.subject.digest
            or sha256(executable).hexdigest() != self.subject.executable_digest
            or (self.subject.kind == "python" and original != executable)
        ):
            raise ValueError("source_changed")
        return executable

    @model_validator(mode="after")
    def integrity(self) -> Self:
        self.executable_bytes()
        if len(set(self.parameters)) != len(self.parameters):
            raise ValueError("worker_duplicate_parameter")
        for bindings in (self.automatic_metrics, self.required_metrics):
            if len({b.name for b in bindings}) != len(bindings):
                raise ValueError("worker_duplicate_metric")
        return self


class WorkerStarted(ExperimentValue):
    phase: Literal["started"] = "started"
    environment: EnvironmentEvidence

    @model_validator(mode="after")
    def observed(self) -> Self:
        if any(
            o.value not in {"runtime", "unknown"} for o in self.environment.origins()
        ):
            raise ValueError("worker_environment_not_runtime")
        return self


class WorkerFinished(ExperimentValue):
    phase: Literal["finished"] = "finished"
    status: Literal["success", "failed", "cancelled"]
    parameters: Annotated[tuple[Parameter, ...], Field(max_length=256)] = ()
    metrics: Annotated[tuple[Metric, ...], Field(max_length=256)] = ()
    diagnostic: (
        Literal[
            "execution_exception",
            "execution_exit",
            "execution_cancelled",
            "metric_capture_failed",
            "worker_failed",
            "source_changed",
            "input_changed",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def runtime_only(self) -> Self:
        if any(p.origin.value != "runtime" for p in self.parameters):
            raise ValueError("worker_parameter_not_runtime")
        if (self.status == "success") != (self.diagnostic is None):
            raise ValueError("worker_status_diagnostic")
        if self.status != "success" and (self.parameters or self.metrics):
            raise ValueError("worker_failed_observations")
        if len({p.name for p in self.parameters}) != len(self.parameters) or len(
            {m.name for m in self.metrics}
        ) != len(self.metrics):
            raise ValueError("worker_duplicate_observation")
        return self
