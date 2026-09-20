"""Container policy, deployment identity and content-bound execution plan."""

from typing import Literal, Self

from pydantic import Field, JsonValue, model_validator

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel
from apizr.execution.model import RuntimePlan, Status
from apizr.execution.policy import Effects, Environment, Limits, Network, Subprocess


class Resources(ValueModel):
    memory_bytes: int = Field(
        default=268435456, strict=True, ge=67108864, le=8589934592
    )
    cpu_millis: int = Field(default=1000, strict=True, ge=10, le=64000)
    pids: int = Field(default=64, strict=True, ge=8, le=1024)
    scratch_bytes: int = Field(default=16777216, strict=True, ge=1048576, le=1073741824)

    @model_validator(mode="after")
    def bounded_scratch(self) -> Self:
        if self.scratch_bytes > self.memory_bytes // 2:
            raise ValueError("Scratch must leave memory for the worker")
        return self


class ExecutionPolicyV2(ValueModel):
    schema_version: Literal["apizr.execution/v2"] = "apizr.execution/v2"
    backend: Literal["oci-container"] = "oci-container"
    limits: Limits = Limits()
    resources: Resources = Resources()
    environment: Environment = Environment()
    network: Network = Network(mode="deny")
    filesystem: Literal["container"] = "container"
    subprocess: Subprocess = Subprocess()
    effects: Effects = Effects()


class RuntimeImage(ValueModel):
    # Full, locally verified image config ID. Tags and abbreviated IDs cannot bind content.
    image: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    platform: Literal["linux/amd64", "linux/arm64"]
    provider: Literal["apizr.docker-engine/v1"] = "apizr.docker-engine/v1"


class ContainerPlan(ValueModel):
    schema_version: Literal["apizr.runtime/v2"] = "apizr.runtime/v2"
    backend_version: Literal["apizr.oci-container/v1"] = "apizr.oci-container/v1"
    policy: ExecutionPolicyV2
    policy_digest: Digest
    runtime: RuntimeImage
    # The immutable v1 worker validates its own bound invocation. Kernel controls
    # surround it; its local policy does not pretend to enforce container controls.
    worker: RuntimePlan
    worker_digest: Digest


ContainerStatus = Literal[
    "backend_unavailable",
    "runtime_image_unavailable",
    "resource_limit",
    "cleanup_failed",
]


class ContainerResult(ValueModel):
    schema_version: Literal["apizr.execution-result/v2"] = "apizr.execution-result/v2"
    status: Status | ContainerStatus
    value: JsonValue = None
