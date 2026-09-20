"""The independently versioned bridge from transport artifacts to execution."""

from typing import Literal

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel


class PlanArtifact(ValueModel):
    path: str
    digest: Digest


class ExecutionBundle(ValueModel):
    schema_version: Literal["apizr.execution-bundle/v1"] = "apizr.execution-bundle/v1"
    backend_version: Literal["apizr.local-process/v1"] = "apizr.local-process/v1"
    transport: Literal["rest", "mcp"]
    contract_digest: Digest
    policy_artifact: Literal["execution/policy.json"] = "execution/policy.json"
    policy_digest: Digest
    capabilities: dict[str, PlanArtifact]
    artifacts: dict[str, Digest]
