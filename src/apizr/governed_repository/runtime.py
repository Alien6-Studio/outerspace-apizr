"""Evidence-bound transport runtime. Never installs the project importer."""

import json
from pathlib import Path
from typing import Literal

from pydantic import JsonValue

from apizr.capabilities.model import Digest
from apizr.execution.model import ExecutionResult
from apizr.execution.policy import (
    ExecutionPolicy,
    PolicyRefused,
    check_controls,
    local_capabilities,
)
from apizr.execution.serialization import digest
from apizr.interfaces.model import InvocationContract
from apizr.interfaces.serialization import json_bytes
from apizr.oci.model import ContainerResult, ExecutionPolicyV2
from apizr.oci.provider import ProviderError
from apizr.repository_execution.docker import RepositoryDockerProvider
from apizr.repository_execution.model import (
    RepositoryContainerPlan,
    RepositoryRuntimePlan,
)
from apizr.repository_execution.planner import evidence, validate_plan, validate_sources
from apizr.repository_execution.supervisor import execute
from apizr.repository_interfaces.model import (
    MCPManifest,
    RepositoryInterface,
    RestManifest,
)
from apizr.repository_interfaces.runtime import RepositoryLoader, read_artifact

from .model import ContainerBundle, ExecutionBundle


class GovernedRuntime:
    def __init__(self, root: Path, transport: Literal["rest", "mcp"]):
        self.root = root
        self.transport = transport
        self.manifest_name = f"apizr-repository-{transport}.json"
        self.container = False
        try:
            self.anchor = Digest.of_bytes(read_artifact(root, self.manifest_name))
            self.plans, _, _, _ = self.validate()
            if isinstance(self.bundle, ContainerBundle):
                RepositoryDockerProvider().probe(self.bundle.runtime)
            else:
                for plan in self.plans.values():
                    assert isinstance(plan, RepositoryRuntimePlan)
                    check_controls(plan.policy, local_capabilities())
        except (
            OSError,
            ValueError,
            RuntimeError,
            KeyError,
            RecursionError,
            ProviderError,
        ):
            raise RuntimeError(
                "Governed repository bundle or backend unavailable"
            ) from None

    def validate(
        self,
    ) -> tuple[
        dict[str, RepositoryRuntimePlan | RepositoryContainerPlan],
        bytes,
        dict[str, bytes],
        dict[str, bytes],
    ]:
        raw = read_artifact(self.root, self.manifest_name)
        if Digest.of_bytes(raw) != self.anchor:
            raise ValueError("Manifest changed")
        manifest = (
            RestManifest if self.transport == "rest" else MCPManifest
        ).model_validate_json(raw)
        artifacts = {
            name: read_artifact(self.root, name) for name in manifest.artifacts
        }
        if any(
            Digest.of_bytes(content) != manifest.artifacts[name]
            for name, content in artifacts.items()
        ):
            raise ValueError("Artifact changed")
        bridge = artifacts["execution/bundle.json"]
        container = (
            json.loads(bridge).get("schema_version")
            == "apizr.repository-execution-bundle/v2"
        )
        bundle = (
            ContainerBundle if container else ExecutionBundle
        ).model_validate_json(bridge)
        if bundle.transport != self.transport or bundle.artifacts != {
            k: v for k, v in manifest.artifacts.items() if k != "execution/bundle.json"
        }:
            raise ValueError("Execution bridge mismatch")
        if "execution/worker.py" not in bundle.artifacts or not any(
            p.startswith("apizr_governed/") for p in bundle.artifacts
        ):
            raise ValueError("Worker closure missing")
        contract = RepositoryInterface.model_validate_json(
            artifacts["repository-interface.json"]
        )
        if (
            contract.interface != self.transport
            or digest(contract) != manifest.repository_interface_digest
            or digest(contract) != bundle.repository_interface_digest
            or manifest.exposure_plan_digest != contract.exposure_plan_digest
            or bundle.exposure_plan_digest != contract.exposure_plan_digest
            or manifest.sources != contract.sources
        ):
            raise ValueError("Repository interface mismatch")
        exposure = artifacts["exposure-plan.json"]
        document = json.loads(exposure)
        evidence(contract, exposure, bundle.backend)
        for field, path in (
            ("catalog_digest", "capability-catalog.json"),
            ("graph_digest", "capability-graph.json"),
            ("repository_readiness_digest", "repository-readiness.json"),
        ):
            if Digest.of_bytes(artifacts[path]) != getattr(contract, field):
                raise ValueError("Upstream evidence mismatch")
        if (
            Digest.of_bytes(artifacts["exposure-policy.json"]).model_dump(mode="json")
            != document["exposure_policy_digest"]
        ):
            raise ValueError("Exposure policy mismatch")
        sources = {s.bundle_path: artifacts[s.bundle_path] for s in contract.sources}
        validate_sources(contract, sources)
        RepositoryLoader(
            self.root, [s.model_dump(mode="json") for s in contract.sources]
        )  # Tree validation only, never install/import.
        policy = (
            ExecutionPolicyV2 if container else ExecutionPolicy
        ).model_validate_json(artifacts[bundle.policy_artifact])
        if digest(policy) != bundle.policy_digest:
            raise ValueError("Execution policy mismatch")
        entries = (
            manifest.endpoints if isinstance(manifest, RestManifest) else manifest.tools
        )
        if (
            Digest.of_bytes(json_bytes([e.model_dump(mode="json") for e in entries]))
            != bundle.contract_digest
        ):
            raise ValueError("Transport contract mismatch")
        if [e.capability_id for e in entries] != [
            c.capability_id for c in contract.capabilities
        ] or set(bundle.capabilities) != {
            c.capability_id for c in contract.capabilities
        }:
            raise ValueError("Public surface mismatch")
        plans: dict[str, RepositoryRuntimePlan | RepositoryContainerPlan] = {}
        for entry, capability in zip(entries, contract.capabilities, strict=True):
            invocation = InvocationContract.model_validate(
                entry.model_dump(include=set(InvocationContract.model_fields))
            )
            if invocation != capability.invocation:
                raise ValueError("Invocation mismatch")
            selected = bundle.capabilities[entry.capability_id]
            plan = (
                RepositoryContainerPlan if container else RepositoryRuntimePlan
            ).model_validate_json(artifacts[selected.path])
            validate_plan(plan, exposure)
            worker = plan.worker if isinstance(plan, RepositoryContainerPlan) else plan
            if (
                worker.execution_context != bundle.backend
                or digest(plan) != selected.digest
                or plan.policy != policy
                or worker.repository_interface != contract
                or worker.interface != invocation
                or worker.capability_id != entry.capability_id
            ):
                raise ValueError("Execution plan mismatch")
            if isinstance(plan, RepositoryContainerPlan) and (
                not isinstance(bundle, ContainerBundle)
                or plan.runtime != bundle.runtime
            ):
                raise ValueError("Runtime image mismatch")
            plans[entry.capability_id] = plan
        self.bundle = bundle
        self.contract = contract
        self.container = container
        return (
            plans,
            exposure,
            sources,
            {
                name: content
                for name, content in artifacts.items()
                if name.startswith("apizr_governed/") or name == "execution/worker.py"
            },
        )

    def invoke(
        self, capability: str, payload: JsonValue
    ) -> ExecutionResult | ContainerResult:
        result_type = ContainerResult if self.container else ExecutionResult
        try:
            plans, exposure, sources, runtime_files = self.validate()
            return execute(
                plans[capability],
                exposure,
                sources,
                payload,
                runtime_files=runtime_files,
            )
        except PolicyRefused:
            return result_type(status="policy_refused")
        except (OSError, ValueError, RuntimeError, KeyError, RecursionError):
            return result_type(status="binding_failed")
