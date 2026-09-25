"""OCI 1.1 delivery-proof profile: six individual, bounded public blobs."""

import os
import time
from pathlib import Path

from apizr_oci.model import BuildError
from apizr_oci.oras import OCI_MANIFEST, Registry, descriptor, sha
from apizr_oci.push import document
from apizr_oci.snapshot import read

from .delivery import (
    FILES,
    MAX_FILE,
    export,
    snapshot,
    tool,
    trust_snapshot,
    verified,
    write,
)
from .model import (
    AttestError,
    DiscoverRequest,
    DiscoverResult,
    FetchRequest,
    FetchResult,
    PublishRequest,
    PublishResult,
)

ARTIFACT_TYPE = "application/vnd.apizr.attest.delivery.v1"
LAYER_TYPE = "application/vnd.apizr.attest.delivery.file.v1"
ANNOTATIONS = {"org.opencontainers.image.created": "1970-01-01T00:00:00Z"}
EMPTY = {
    "mediaType": "application/vnd.oci.empty.v1+json",
    "digest": sha(b"{}"),
    "size": 2,
    "data": "e30=",
}


def manifest_files(raw: bytes, subject: dict) -> dict[str, dict]:
    value = document(raw)
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schemaVersion",
            "mediaType",
            "artifactType",
            "config",
            "layers",
            "subject",
            "annotations",
        }
        or value["schemaVersion"] != 2
        or value["mediaType"] != OCI_MANIFEST
        or value["artifactType"] != ARTIFACT_TYPE
        or value["subject"] != subject
        or value["config"] != EMPTY
        or value["annotations"] != ANNOTATIONS
        or not isinstance(value["layers"], list)
        or len(value["layers"]) != len(FILES)
    ):
        raise AttestError("invalid_proof_manifest")
    found = {}
    for entry in value["layers"]:
        desc = descriptor(entry, maximum=MAX_FILE, allowed={"annotations"})
        annotations = entry.get("annotations")
        if not isinstance(annotations, dict) or set(annotations) != {
            "org.opencontainers.image.title"
        }:
            raise AttestError("invalid_proof_paths")
        name = annotations["org.opencontainers.image.title"]
        if (
            not isinstance(name, str)
            or name not in FILES
            or name in found
            or desc["mediaType"] != LAYER_TYPE
        ):
            raise AttestError("invalid_proof_paths")
        found[name] = desc
    if list(found) != sorted(FILES):
        raise AttestError("invalid_proof_order")
    return found


def registry(request, work, deadline):
    transport_work = work / "transport"
    transport_work.mkdir(mode=0o700)
    return Registry(
        request.transport, request.expected_reference, transport_work, deadline
    )


def check_proof(request, work: Path, proof: Path, deadline: float, original: Path):
    trust = work / "trust"
    trust_snapshot(Path(request.trust_store), trust, original)
    executable = tool(request, work, deadline)
    return verified(request, executable, proof, trust, deadline)


def execute_publish(request: PublishRequest, work: Path) -> PublishResult:
    deadline = time.monotonic() + request.timeout_ms / 1000
    proof = work / "proof"
    snapshot(Path(request.proof_dir), proof)
    verification = check_proof(request, work, proof, deadline, Path(request.proof_dir))
    client = registry(request, work, deadline)
    _, subject = client.manifest(request.expected_reference)
    client.discover(ARTIFACT_TYPE)  # force API support/auth before any transfer
    try:
        reply = document(
            client.call(
                [
                    "attach",
                    "--distribution-spec",
                    "v1.1-referrers-api",
                    "--artifact-type",
                    ARTIFACT_TYPE,
                    "--annotation",
                    "org.opencontainers.image.created=1970-01-01T00:00:00Z",
                    "--concurrency",
                    "1",
                    "--format",
                    "json",
                    request.expected_reference,
                    *[name + ":" + LAYER_TYPE for name in sorted(FILES)],
                ],
                cwd=proof,
            )
        )
        desc = descriptor(reply, allowed={"reference", "artifactType", "annotations"})
        reference = client.repository + "@" + desc["digest"]
        if (
            reply.get("reference") != reference
            or reply.get("artifactType") != ARTIFACT_TYPE
        ):
            raise AttestError("invalid_oras_attach_result")
        raw, actual = client.manifest(reference)
        if actual != desc:
            raise AttestError("artifact_descriptor_mismatch")
        files = manifest_files(raw, subject)
        for name in FILES:
            source = read(proof, name, MAX_FILE)
            if files[name]["size"] != len(source) or files[name]["digest"] != sha(
                source
            ):
                raise AttestError("artifact_content_mismatch")
        if not any(c["reference"] == reference for c in client.discover(ARTIFACT_TYPE)):
            raise AttestError("artifact_not_discoverable")
        return PublishResult(
            image_reference=request.expected_reference,
            image_digest=subject["digest"],
            artifact_reference=reference,
            artifact_manifest_digest=desc["digest"],
            receipt_sha256=verification.receipt_sha256,
            verification=verification,
        )
    except (
        AttestError,
        BuildError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RecursionError,
    ):
        return PublishResult(
            image_reference=request.expected_reference,
            image_digest=subject["digest"],
            receipt_sha256=verification.receipt_sha256,
            verification=verification,
            state="remote_state_unconfirmed",
            receipt_published=False,
        )


def execute_discover(request: DiscoverRequest, work: Path) -> DiscoverResult:
    client = registry(request, work, time.monotonic() + request.timeout_ms / 1000)
    client.manifest(request.expected_reference)
    return DiscoverResult.model_validate(
        {
            "image_reference": request.expected_reference,
            "candidates": client.discover(ARTIFACT_TYPE),
        }
    )


def execute_fetch(request: FetchRequest, work: Path) -> FetchResult:
    deadline = time.monotonic() + request.timeout_ms / 1000
    output = Path(request.output_dir)
    if os.path.lexists(output):
        raise AttestError("proof_already_exists")
    if (
        request.artifact_reference.split("@")[0]
        != request.expected_reference.split("@")[0]
    ):
        raise AttestError("cross_repository_refused")
    client = registry(request, work, deadline)
    _, subject = client.manifest(request.expected_reference)
    raw, desc = client.manifest(request.artifact_reference)
    files = manifest_files(raw, subject)
    proof = work / "proof"
    for name in FILES:
        write(proof / name, client.blob(files[name]))
    verification = check_proof(request, work, proof, deadline, output)
    export(proof, output)
    return FetchResult(
        image_reference=request.expected_reference,
        image_digest=subject["digest"],
        artifact_reference=request.artifact_reference,
        artifact_manifest_digest=desc["digest"],
        receipt_sha256=verification.receipt_sha256,
        verification=verification,
    )
