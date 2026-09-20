"""Integrity-checked OCI bridge. Only the container worker imports user source."""

from pathlib import Path
from typing import Literal

from pydantic import JsonValue

from apizr.capabilities.model import Digest
from apizr.execution.serialization import digest
from apizr.governed.runtime import Manifest, artifact
from apizr.interfaces.model import InvocationContract
from apizr.interfaces.planner import BoundSource
from apizr.interfaces.serialization import json_bytes
from apizr.oci.docker import DockerProvider
from apizr.oci.model import ContainerPlan, ContainerResult, ExecutionPolicyV2
from apizr.oci.planner import validate_plan
from apizr.oci.provider import ProviderError
from apizr.oci.supervisor import execute

from .model import REQUIRED_FILES, ExecutionBundle


class GovernedRuntime:
    def __init__(self, root: Path, transport: Literal["rest", "mcp"]):
        self.root = root
        self.transport = transport
        self.manifest_name = f"apizr-{transport}.json"
        try:
            self.anchor = Digest.of_bytes(artifact(root, self.manifest_name))
            self.bundle = self.check_artifacts()
            self.plans, self.original, self.executable = self.validate_plans()
            DockerProvider().probe(self.bundle.runtime)
        except (OSError, ValueError, KeyError, RecursionError, ProviderError):
            raise RuntimeError(
                "OCI governed execution bundle or provider unavailable or invalid"
            ) from None

    def check_artifacts(self) -> ExecutionBundle:
        raw = artifact(self.root, self.manifest_name)
        if Digest.of_bytes(raw) != self.anchor:
            raise ValueError("Manifest changed")
        manifest = Manifest.model_validate_json(raw)
        if manifest.schema_version != f"apizr.{self.transport}/v1":
            raise ValueError("Transport mismatch")
        bridge = artifact(self.root, "execution/bundle.json")
        if Digest.of_bytes(bridge) != manifest.artifacts["execution/bundle.json"]:
            raise ValueError("Bridge digest mismatch")
        bundle = ExecutionBundle.model_validate_json(bridge)
        if bundle.transport != self.transport or not bundle.capabilities:
            raise ValueError("Bridge transport mismatch")
        expected = {
            name: value
            for name, value in manifest.artifacts.items()
            if name != "execution/bundle.json"
        }
        if expected != bundle.artifacts or not set(REQUIRED_FILES) <= set(expected):
            raise ValueError("Incomplete bridge")
        for name, expected_digest in bundle.artifacts.items():
            if Digest.of_bytes(artifact(self.root, name)) != expected_digest:
                raise ValueError("Artifact digest mismatch")
        return bundle

    def validate_plans(self) -> tuple[dict[str, ContainerPlan], bytes, bytes]:
        manifest = Manifest.model_validate_json(artifact(self.root, self.manifest_name))
        policy = ExecutionPolicyV2.model_validate_json(
            artifact(self.root, self.bundle.policy_artifact)
        )
        if digest(policy) != self.bundle.policy_digest:
            raise ValueError("Policy digest mismatch")
        executable = artifact(self.root, manifest.executable_path)
        original = (
            artifact(self.root, "notebook.ipynb")
            if manifest.source.kind == "notebook"
            else executable
        )
        contracts = (
            manifest.capabilities if self.transport == "rest" else manifest.tools
        )
        if Digest.of_bytes(json_bytes(list(contracts))) != self.bundle.contract_digest:
            raise ValueError("Contract digest mismatch")
        plans: dict[str, ContainerPlan] = {}
        for entry in contracts:
            invocation = InvocationContract.model_validate(
                {name: entry[name] for name in InvocationContract.model_fields}
            )
            selected = self.bundle.capabilities[invocation.capability_id]
            runtime = ContainerPlan.model_validate_json(
                artifact(self.root, selected.path)
            )
            if (
                digest(runtime) != selected.digest
                or runtime.policy_digest != self.bundle.policy_digest
            ):
                raise ValueError("Plan digest mismatch")
            validate_plan(runtime, original, executable)
            worker = runtime.worker
            if (
                worker.interface != invocation
                or runtime.policy != policy
                or runtime.runtime != self.bundle.runtime
                or worker.capability_id in plans
            ):
                raise ValueError("Plan linkage mismatch")
            if BoundSource.model_validate(
                worker.model_dump(include=set(BoundSource.model_fields))
            ) != BoundSource.model_validate(
                manifest.model_dump(include=set(BoundSource.model_fields))
            ):
                raise ValueError("Source linkage mismatch")
            if (
                Digest.of_bytes(artifact(self.root, "capability-ir.json"))
                != worker.ir_digest
                or Digest.of_bytes(artifact(self.root, "readiness.json"))
                != worker.readiness_digest
            ):
                raise ValueError("Inspection linkage mismatch")
            plans[worker.capability_id] = runtime
        if set(plans) != set(self.bundle.capabilities):
            raise ValueError("Capability set mismatch")
        return plans, original, executable

    def invoke(self, capability: str, payload: JsonValue) -> ContainerResult:
        try:
            self.check_artifacts()
            selected = self.plans[capability]
        except (OSError, ValueError, KeyError, RecursionError):
            return ContainerResult(status="binding_failed")
        # Reuse the serialized per-capability plan cached at startup. The existing
        # OCI executor still validates its content binding before each invocation.
        return execute(selected, self.original, payload, executable=self.executable)
