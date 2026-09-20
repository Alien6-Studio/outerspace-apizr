"""Content-bound runtime plans and sanitized public execution outcomes."""

from typing import Literal

from pydantic import JsonValue

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel
from apizr.inspection import Inspection
from apizr.interfaces.model import InvocationContract
from apizr.interfaces.planner import BoundSource

from .policy import ExecutionPolicy

Status = Literal[
    "success",
    "invalid_input",
    "timeout",
    "worker_failed",
    "binding_failed",
    "policy_refused",
    "result_invalid",
    "execution_failed",
    "output_limit",
    "source_mismatch",
]


class RuntimePlan(BoundSource):
    schema_version: Literal["apizr.runtime/v1"] = "apizr.runtime/v1"
    backend_version: Literal["apizr.local-process/v1"] = "apizr.local-process/v1"
    capability_id: str
    interface: InvocationContract
    interface_digest: Digest
    policy: ExecutionPolicy
    policy_digest: Digest
    inspection: Inspection


class ExecutionResult(ValueModel):
    schema_version: Literal["apizr.execution-result/v1"] = "apizr.execution-result/v1"
    status: Status
    value: JsonValue = None


class Request(ValueModel):
    plan: RuntimePlan
    plan_digest: Digest
    arguments: JsonValue
