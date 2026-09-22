"""Independent versioned transport-to-repository-execution bridges."""

from typing import Literal

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel
from apizr.oci.model import RuntimeImage


class PlanArtifact(ValueModel):
    path: str
    digest: Digest


class Bridge(ValueModel):
    transport: Literal["rest", "mcp"]
    repository_interface_digest: Digest
    exposure_plan_digest: Digest
    contract_digest: Digest
    policy_artifact: Literal["execution/policy.json"] = "execution/policy.json"
    policy_digest: Digest
    capabilities: dict[str, PlanArtifact]
    artifacts: dict[str, Digest]


class ExecutionBundle(Bridge):
    schema_version: Literal["apizr.repository-execution-bundle/v1"] = (
        "apizr.repository-execution-bundle/v1"
    )
    backend: Literal["local-process"] = "local-process"
    backend_version: Literal["apizr.local-process/v1"] = "apizr.local-process/v1"
    policy_version: Literal["apizr.execution/v1"] = "apizr.execution/v1"


class ContainerBundle(Bridge):
    schema_version: Literal["apizr.repository-execution-bundle/v2"] = (
        "apizr.repository-execution-bundle/v2"
    )
    backend: Literal["oci-container"] = "oci-container"
    backend_version: Literal["apizr.oci-container/v1"] = "apizr.oci-container/v1"
    policy_version: Literal["apizr.execution/v2"] = "apizr.execution/v2"
    provider_version: Literal["apizr.docker-engine/v1"] = "apizr.docker-engine/v1"
    runtime: RuntimeImage
