"""Independent repository worker and OCI contracts; shared public results."""

from typing import Literal

from pydantic import JsonValue

from apizr.capabilities.model import Digest, Effects
from apizr.capabilities.types import ValueModel
from apizr.execution.policy import ExecutionPolicy
from apizr.interfaces.model import InvocationContract
from apizr.oci.model import ExecutionPolicyV2, RuntimeImage
from apizr.repository_interfaces.model import RepositoryInterface


class RepositoryRuntimePlan(ValueModel):
    schema_version: Literal["apizr.repository-runtime/v1"] = (
        "apizr.repository-runtime/v1"
    )
    backend_version: Literal["apizr.local-process/v1"] = "apizr.local-process/v1"
    # Compatibility context only; the worker never claims kernel enforcement.
    execution_context: Literal["local-process", "oci-container"] = "local-process"
    repository_interface: RepositoryInterface
    repository_interface_digest: Digest
    exposure_plan_digest: Digest
    source_universe_digest: Digest
    capability_id: str
    interface: InvocationContract
    interface_digest: Digest
    effects: Effects
    policy: ExecutionPolicy
    policy_digest: Digest


class RepositoryContainerPlan(ValueModel):
    schema_version: Literal["apizr.repository-runtime/v2"] = (
        "apizr.repository-runtime/v2"
    )
    backend_version: Literal["apizr.oci-container/v1"] = "apizr.oci-container/v1"
    policy: ExecutionPolicyV2
    policy_digest: Digest
    runtime: RuntimeImage
    worker: RepositoryRuntimePlan
    worker_digest: Digest


class Request(ValueModel):
    plan: RepositoryRuntimePlan
    plan_digest: Digest
    arguments: JsonValue
