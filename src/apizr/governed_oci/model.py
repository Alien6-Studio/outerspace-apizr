"""Explicit v2 bridge for OCI-governed transport; v1 remains independent."""

from typing import Literal

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel
from apizr.oci.model import RuntimeImage


class PlanArtifact(ValueModel):
    path: str
    digest: Digest


class ExecutionBundle(ValueModel):
    schema_version: Literal["apizr.execution-bundle/v2"] = "apizr.execution-bundle/v2"
    backend: Literal["oci-container"] = "oci-container"
    backend_version: Literal["apizr.oci-container/v1"] = "apizr.oci-container/v1"
    policy_version: Literal["apizr.execution/v2"] = "apizr.execution/v2"
    provider_version: Literal["apizr.docker-engine/v1"] = "apizr.docker-engine/v1"
    runtime: RuntimeImage
    transport: Literal["rest", "mcp"]
    contract_digest: Digest
    policy_artifact: Literal["execution/policy.json"] = "execution/policy.json"
    policy_digest: Digest
    capabilities: dict[str, PlanArtifact]
    artifacts: dict[str, Digest]


OCI_MODULES = (
    "oci/__init__.py",
    "oci/model.py",
    "oci/planner.py",
    "oci/provider.py",
    "oci/docker.py",
    "oci/supervisor.py",
)
BRIDGE_MODULES = (
    "governed_oci/__init__.py",
    "governed_oci/model.py",
    "governed_oci/runtime.py",
)
# These are necessary before a server can accept calls. Every additional emitted
# file is also checked by its manifest-bound digest, including the adapter.
REQUIRED_FILES = (
    "execution/worker.py",
    "capability-ir.json",
    "readiness.json",
    *("apizr_governed/" + name for name in (*OCI_MODULES, *BRIDGE_MODULES)),
    *(
        "apizr_governed/execution/" + name + ".py"
        for name in (
            "worker",
            "protocol",
            "model",
            "planner",
            "policy",
            "invocation",
            "serialization",
            "supervisor",
        )
    ),
)
