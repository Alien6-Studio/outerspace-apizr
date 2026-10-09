"""Explicit remote-proof verification followed by destination admission.

Transfer and proof publication already happened. Never infer a proof selection,
re-sign, upload image layers, or delete remote state as compensation.
"""

import time
from pathlib import Path

from apizr_oci.model import BuildError, PushRequest, PushResult
from apizr_oci.push import (
    LABEL,
    authentication,
    document,
    promote_verified,
    secure_daemon,
)

from apizr.contracts.delivery import PLAN_LABEL, PROOF_LABEL, identity

from .artifacts import fetch_verified
from .delivery import MAX_FILE, file_bytes, read, results
from .model import AdmissionResult, AdmitRequest, AttestError


def execute_admit(request: AdmitRequest, work: Path) -> AdmissionResult:
    request = AdmitRequest.model_validate(request.model_dump(by_alias=True))
    deadline = time.monotonic() + request.timeout_ms / 1000
    expected = PushResult.model_validate(document(file_bytes(request.push_result)))
    if (
        expected.destination != request.destination
        or expected.digest_reference != request.expected_reference
        or expected.delivery_manifest_digest != identity(request.delivery_manifest)
        or expected.delivery_plan_digest
        != request.delivery_manifest.delivery_plan_digest
        or expected.proof_requirement != "required"
        or expected.transfer_verified is not True
        or expected.destination_promoted is not False
        or expected.delivery_admitted is not False
    ):
        raise AttestError("required_transfer_mismatch")
    client, subject, artifact, proof, verification = fetch_verified(
        request, work, deadline, Path(request.push_result), require_discoverable=True
    )
    built, pushed = results(
        read(proof, "delivery/build.json", MAX_FILE),
        read(proof, "delivery/push.json", MAX_FILE),
        request.expected_reference,
    )
    if (
        pushed != expected
        or built.delivery_manifest != request.delivery_manifest
        or built.delivery_plan is None
        or built.delivery_plan.proof_requirement != "required"
        or verification.delivery_manifest_digest != expected.delivery_manifest_digest
        or verification.delivery_plan_digest != expected.delivery_plan_digest
    ):
        raise AttestError("admission_lineage_mismatch")
    # Re-fetch immutable image/config bytes, not an untrusted local publication
    # JSON. Registry.blob verifies descriptor size and digest before parsing.
    image_raw, image_descriptor = client.manifest(request.expected_reference)
    image = document(image_raw)
    config = document(client.blob(image["config"]))
    if (
        image_descriptor != subject
        or image_descriptor["digest"] != pushed.manifest_digest
        or image["config"]["digest"] != pushed.config_digest
        or pushed.image_id not in {pushed.manifest_digest, pushed.config_digest}
        or config["os"] + "/" + config["architecture"] != pushed.platform
        or config["config"]["User"] != "65532:65532"
        or config["config"]["Labels"].get(LABEL) != pushed.inputs_sha256
        or config["config"]["Labels"].get(PLAN_LABEL)
        != identity(built.delivery_plan).value
        or config["config"]["Labels"].get(PROOF_LABEL) != "required"
    ):
        raise AttestError("admission_image_mismatch")
    promotion = PushRequest(
        schema="apizr.oci-push/v1",
        image_id=pushed.image_id,
        platform=request.delivery_manifest.platform,
        inputs_sha256=pushed.inputs_sha256,
        destination=request.destination,
        docker=request.docker,
        authentication=request.transport.authentication,
        delivery_manifest=request.delivery_manifest,
        delivery_plan=built.delivery_plan,
        max_log_bytes=request.max_output_bytes,
    )
    promotion_work = work / "promotion"
    promotion_work.mkdir(mode=0o700)
    authentication(promotion, promotion_work)
    secure_daemon(promotion, promotion_work, deadline, None)
    state = "admitted"
    try:
        promote_verified(
            promotion,
            promotion_work,
            (pushed.config_digest, pushed.manifest_digest),
            deadline,
        )
    except BuildError as error:
        if str(error) != "remote_state_unconfirmed":
            raise
        state = "remote_state_unconfirmed"
    return AdmissionResult(
        state=state,
        destination=request.destination,
        image_reference=request.expected_reference,
        delivery_plan_digest=identity(built.delivery_plan),
        delivery_manifest_digest=identity(request.delivery_manifest),
        proof_artifact_reference=request.artifact_reference,
        proof_artifact_manifest_digest=artifact["digest"],
        receipt_sha256=verification.receipt_sha256,
        signer=verification.signer,
        destination_promoted=True if state == "admitted" else None,
        delivery_admitted=state == "admitted",
    )
