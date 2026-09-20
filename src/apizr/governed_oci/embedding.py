"""Extend existing source embedding without changing any v1 artifact bytes."""

import json
from typing import Literal

from apizr.capabilities.model import Digest
from apizr.execution.serialization import canonical_bytes, digest
from apizr.governed.embedding import definition, source
from apizr.governed.embedding import runtime_files as local_files
from apizr.inspection import Inspection
from apizr.interfaces.serialization import json_bytes
from apizr.oci.model import ExecutionPolicyV2, RuntimeImage
from apizr.oci.planner import plan

from .model import BRIDGE_MODULES, OCI_MODULES, ExecutionBundle, PlanArtifact


def runtime_files(transport: Literal["rest", "mcp"]) -> dict[str, bytes]:
    artifacts = local_files(transport)
    del artifacts["apizr_governed/governed/model.py"]
    del artifacts[f"apizr_governed/governed/{transport}.py"]
    # Only the shared manifest/path utilities are used from the v1 bridge; copy
    # their actual definitions, as the existing embedding does for Inspection.
    utilities = (
        "from pathlib import Path, PurePosixPath\nfrom typing import Literal\n"
        "from pydantic import JsonValue\nfrom apizr.capabilities.model import Digest\n"
        "from apizr.interfaces.planner import BoundSource\n\n"
        + definition("governed/runtime.py", "Manifest")
        + "\n"
        + definition("governed/runtime.py", "artifact")
    )
    artifacts["apizr_governed/governed/runtime.py"] = utilities.replace(
        "from apizr.", "from apizr_governed."
    ).encode()
    for name in (*OCI_MODULES, *BRIDGE_MODULES, f"governed_oci/{transport}.py"):
        artifacts["apizr_governed/" + name] = (
            source(name).replace("from apizr.", "from apizr_governed.").encode("utf-8")
        )
    entry = "app.py" if transport == "rest" else "server.py"
    artifacts[entry] = artifacts[entry].replace(
        f"apizr_governed.governed.{transport}".encode(),
        f"apizr_governed.governed_oci.{transport}".encode(),
    )
    return artifacts


def govern(
    artifacts: dict[str, bytes],
    inspection: Inspection,
    source_bytes: bytes,
    executable: bytes,
    policy: ExecutionPolicyV2,
    runtime_image: RuntimeImage,
    transport: Literal["rest", "mcp"],
) -> dict[str, bytes]:
    artifacts.pop("apizr_runtime.py", None)
    manifest_name = f"apizr-{transport}.json"
    manifest = json.loads(artifacts.pop(manifest_name))
    contracts = manifest["capabilities" if transport == "rest" else "tools"]
    policy = ExecutionPolicyV2.model_validate(policy.model_dump(mode="json"))
    runtime_image = RuntimeImage.model_validate(runtime_image.model_dump(mode="json"))
    plans: dict[str, PlanArtifact] = {}
    for contract in contracts:
        runtime = plan(
            inspection,
            source_bytes,
            contract["capability_id"],
            policy,
            runtime_image,
            executable=executable,
        )
        path = "execution/plans/" + runtime.worker.interface.name + ".json"
        artifacts[path] = canonical_bytes(runtime)
        plans[runtime.worker.capability_id] = PlanArtifact(
            path=path, digest=digest(runtime)
        )
    artifacts.update(runtime_files(transport))
    artifacts["execution/policy.json"] = canonical_bytes(policy)
    artifacts["requirements.txt"] += b"pydantic>=2.12,<3\n"
    bundle = ExecutionBundle(
        transport=transport,
        runtime=runtime_image,
        contract_digest=Digest.of_bytes(json_bytes(contracts)),
        policy_digest=digest(policy),
        capabilities=dict(sorted(plans.items())),
        artifacts={
            name: Digest.of_bytes(content)
            for name, content in sorted(artifacts.items())
        },
    )
    artifacts["execution/bundle.json"] = canonical_bytes(bundle)
    manifest["artifacts"] = {
        name: Digest.of_bytes(content).model_dump(mode="json")
        for name, content in sorted(artifacts.items())
    }
    artifacts[manifest_name] = json_bytes(manifest)
    return dict(sorted(artifacts.items()))
