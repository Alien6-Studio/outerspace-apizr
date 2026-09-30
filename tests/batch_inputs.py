"""SDK-free prepared batch inputs shared by contract tests and installed proofs."""

import json

from apizr.capabilities.model import Digest
from apizr.delivery import DeliveryManifest, DeliveryPlan, identity
from apizr.delivery_batch import BatchRequest
from apizr.delivery_results import BuildResult

D = Digest(algorithm="sha256", value="b" * 64)
IMAGE = "sha256:" + "a" * 64
SIGNER = "e" * 64


def request(tmp_path, required=True, count=3):
    fields = {name: D for name in DeliveryPlan.model_fields if name.endswith("_digest")}
    plan = DeliveryPlan(
        **fields,
        proof_requirement="required" if required else "optional",
        source={"kind": "local", "repository_digest": D},
        interface="rest",
        dependency_closure=({"name": "six", "version": "1.17.0", "sha256": "a" * 64},),
        build_tools=tuple(
            {"name": name, "version": "0.4.2rc1"}
            for name in ("outerspace-apizr", "outerspace-apizr-oci")
        ),
        platform="linux/amd64",
        base_image="python@sha256:" + "a" * 64,
    )
    manifest = DeliveryManifest(
        delivery_plan_digest=identity(plan),
        image_id=IMAGE,
        platform=plan.platform,
        inputs_sha256="b" * 64,
    )
    build = BuildResult(
        tag="service:local",
        image_id=IMAGE,
        platform=plan.platform,
        inputs_sha256=manifest.inputs_sha256,
        delivery_plan=plan,
        delivery_manifest=manifest,
        delivery_manifest_digest=identity(manifest),
    )
    destinations = []
    for i in range(count):
        destinations.append(
            {
                "push": {
                    "schema": "apizr.oci-push/v1",
                    "image_id": IMAGE,
                    "platform": plan.platform,
                    "inputs_sha256": manifest.inputs_sha256,
                    "delivery_plan": plan.model_dump(mode="json"),
                    "delivery_manifest": manifest.model_dump(mode="json"),
                    "destination": f"registry.example/team/service-{i}:v1",
                    "docker": {
                        "executable": "/private/docker",
                        "socket": "/private/daemon.sock",
                    },
                    "authentication": {"config_file": f"/private/auth-{i}.json"},
                },
                "proof": {
                    "verification": {
                        "expected_signer": SIGNER,
                        "trust_store": "/private/trust",
                        "tool": {
                            "executable": "/private/attest",
                            "version": "0.1.0",
                            "sha256": "f" * 64,
                        },
                    },
                    "signing": {
                        "key_file": "/private/key",
                        "key_id": "e" * 32,
                        "tsa_url": "https://tsa.example/timestamp",
                    },
                    "transport": {
                        "authentication": {"config_file": f"/private/oras-{i}.json"},
                        "tool": {
                            "executable": "/private/oras",
                            "version": "1.3.4",
                            "sha256": "f" * 64,
                        },
                    },
                }
                if required
                else None,
            }
        )
    return BatchRequest.model_validate_json(
        json.dumps(
            {
                "schema": "apizr.delivery-batch-request/v1",
                "build": build.model_dump(mode="json", by_alias=True),
                "destinations": destinations,
                "evidence_root": str(tmp_path / "evidence"),
            }
        )
    )
