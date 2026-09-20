"""Static bundle verification and transport-neutral governed calls; no source import."""

import sys
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import JsonValue

from apizr.capabilities.model import Digest
from apizr.execution.model import ExecutionResult, RuntimePlan
from apizr.execution.planner import validate_plan
from apizr.execution.policy import (
    ExecutionPolicy,
    PolicyRefused,
    check_controls,
    local_capabilities,
)
from apizr.execution.serialization import digest
from apizr.execution.supervisor import execute
from apizr.interfaces.model import InvocationContract
from apizr.interfaces.planner import BoundSource
from apizr.interfaces.serialization import json_bytes

from .model import ExecutionBundle


class Manifest(BoundSource):
    schema_version: Literal["apizr.rest/v1", "apizr.mcp/v1"]
    capabilities: tuple[dict[str, JsonValue], ...] = ()
    tools: tuple[dict[str, JsonValue], ...] = ()
    protocol: dict[str, JsonValue] | None = None
    artifacts: dict[str, Digest]


def artifact(root: Path, name: str) -> bytes:
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or path.as_posix() != name
        or ".." in path.parts
        or "\\" in name
    ):
        raise ValueError("Invalid artifact path")
    target = root / name
    if not target.resolve(strict=True).is_relative_to(root.resolve()):
        raise ValueError("Invalid artifact path")
    return target.read_bytes()


class GovernedRuntime:
    def __init__(self, root: Path, transport: Literal["rest", "mcp"]):
        self.root = root
        self.transport = transport
        self.manifest_name = f"apizr-{transport}.json"
        try:
            self.anchor = Digest.of_bytes(artifact(root, self.manifest_name))
            self.plans, _, _ = self.validate()
        except (OSError, ValueError, KeyError, RecursionError):
            raise RuntimeError(
                "Governed execution bundle unavailable or invalid"
            ) from None

    def validate(self) -> tuple[dict[str, RuntimePlan], bytes, bytes]:
        raw = artifact(self.root, self.manifest_name)
        if Digest.of_bytes(raw) != self.anchor:
            raise ValueError("Transport manifest changed")
        manifest = Manifest.model_validate_json(raw)
        if manifest.schema_version != f"apizr.{self.transport}/v1":
            raise ValueError("Transport mismatch")
        bridge = artifact(self.root, "execution/bundle.json")
        if Digest.of_bytes(bridge) != manifest.artifacts["execution/bundle.json"]:
            raise ValueError("Bundle digest mismatch")
        bundle = ExecutionBundle.model_validate_json(bridge)
        if bundle.transport != self.transport or not bundle.capabilities:
            raise ValueError("Bundle transport mismatch")
        expected = {
            name: value
            for name, value in manifest.artifacts.items()
            if name != "execution/bundle.json"
        }
        if expected != bundle.artifacts or "execution/worker.py" not in expected:
            raise ValueError("Incomplete bundle")
        for name, expected_digest in bundle.artifacts.items():
            if Digest.of_bytes(artifact(self.root, name)) != expected_digest:
                raise ValueError("Artifact digest mismatch")
        policy = ExecutionPolicy.model_validate_json(
            artifact(self.root, bundle.policy_artifact)
        )
        if digest(policy) != bundle.policy_digest:
            raise ValueError("Policy digest mismatch")
        check_controls(policy, local_capabilities())
        executable = artifact(self.root, manifest.executable_path)
        original = (
            artifact(self.root, "notebook.ipynb")
            if manifest.source.kind == "notebook"
            else executable
        )
        contracts = (
            manifest.capabilities if self.transport == "rest" else manifest.tools
        )
        if Digest.of_bytes(json_bytes(list(contracts))) != bundle.contract_digest:
            raise ValueError("Contract digest mismatch")
        plans: dict[str, RuntimePlan] = {}
        for entry in contracts:
            invocation = InvocationContract.model_validate(
                {name: entry[name] for name in InvocationContract.model_fields}
            )
            selected = bundle.capabilities[invocation.capability_id]
            runtime = RuntimePlan.model_validate_json(
                artifact(self.root, selected.path)
            )
            if (
                digest(runtime) != selected.digest
                or runtime.policy_digest != bundle.policy_digest
            ):
                raise ValueError("Plan digest mismatch")
            validate_plan(runtime, original, executable)
            if (
                runtime.interface != invocation
                or runtime.policy != policy
                or runtime.capability_id in plans
            ):
                raise ValueError("Plan interface mismatch")
            if BoundSource.model_validate(
                runtime.model_dump(include=set(BoundSource.model_fields))
            ) != BoundSource.model_validate(
                manifest.model_dump(include=set(BoundSource.model_fields))
            ):
                raise ValueError("Source linkage mismatch")
            if (
                Digest.of_bytes(artifact(self.root, "capability-ir.json"))
                != runtime.ir_digest
                or Digest.of_bytes(artifact(self.root, "readiness.json"))
                != runtime.readiness_digest
            ):
                raise ValueError("Inspection linkage mismatch")
            plans[runtime.capability_id] = runtime
        if set(plans) != set(bundle.capabilities):
            raise ValueError("Capability set mismatch")
        return plans, original, executable

    def invoke(self, capability: str, payload: JsonValue) -> ExecutionResult:
        try:
            plans, original, executable = self.validate()
            selected = plans[capability]
        except PolicyRefused:
            return ExecutionResult(status="policy_refused")
        except (OSError, ValueError, KeyError, RecursionError):
            return ExecutionResult(status="binding_failed")
        return execute(
            selected,
            original,
            payload,
            executable=executable,
            worker_command=[
                sys.executable,
                "-I",
                str((self.root / "execution/worker.py").resolve()),
            ],
        )
