"""Bounded operational requests and portable, independently typed outcomes."""

import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from apizr.capabilities.model import Digest
from apizr.delivery import DeliveryManifest, ProofRequirement, identity
from apizr.delivery_results import (
    AdmissionResult,
    BuildResult,
    DeliveryResult,
    PublishResult,
    PushResult,
)
from apizr.operator_policy import repository_name
from apizr.publication_contracts import (
    Docker,
    Model,
    PushRequest,
    SigningInputs,
    Transport,
    VerificationInputs,
    digest_reference,
)

MAX_DESTINATIONS = 8


def destination_key(value: str) -> str:
    repository, tag = PushRequest.reference(value).rsplit(":", 1)
    return repository_name(repository) + ":" + tag


class ProofInputs(Model):
    verification: VerificationInputs
    signing: SigningInputs
    transport: Transport


class Destination(Model):
    push: PushRequest
    proof: ProofInputs | None = None
    # Only explicit operator recovery identities, never discovered candidates.
    recovery_reference: str | None = None
    selected_artifact: str | None = None

    @model_validator(mode="after")
    def recovery_repository(self):
        for value in (self.recovery_reference, self.selected_artifact):
            if value is not None:
                digest_reference(value)
                if value.split("@")[0] != self.push.destination.rsplit(":", 1)[0]:
                    raise ValueError(
                        "Recovery requires the exact destination repository"
                    )
        return self


class BatchRequest(Model):
    schema_version: Literal["apizr.delivery-batch-request/v1"] = Field(alias="schema")
    build: BuildResult
    destinations: tuple[Destination, ...] = Field(
        min_length=1, max_length=MAX_DESTINATIONS
    )
    evidence_root: str
    _root = field_validator("evidence_root")(Docker.absolute.__func__)

    @model_validator(mode="after")
    def shared_identity(self):
        build = self.build
        if build.delivery_plan is None or build.delivery_manifest is None:
            raise ValueError("Qualified build lineage required")
        keys = [destination_key(d.push.destination) for d in self.destinations]
        if len(set(keys)) != len(keys):
            raise ValueError("Unique destinations required")
        for destination in self.destinations:
            push = destination.push
            if (
                (push.image_id, push.platform, push.inputs_sha256)
                != (build.image_id, build.platform, build.inputs_sha256)
                or push.delivery_plan != build.delivery_plan
                or push.delivery_manifest != build.delivery_manifest
                or (destination.proof is not None)
                != (build.delivery_plan.proof_requirement == "required")
                or (
                    destination.selected_artifact is not None
                    and destination.proof is None
                )
            ):
                raise ValueError(
                    "Every destination must use the same qualified build and proof requirement"
                )
        return self


Stage = Literal[
    "not_started",
    "transferred",
    "proof_created",
    "proof_published",
    "admitted",
    "complete",
]
Operation = Literal["push", "attest", "publish", "admit", "observe", "verify"]
Diagnostic = Literal[
    "authorization_refused",
    "transfer_failed",
    "remote_state_unconfirmed",
    "attestation_failed",
    "proof_publication_failed",
    "admission_failed",
    "destination_conflict",
    "destination_absent",
    "cancelled",
    "evidence_invalid",
    "proof_selection_required",
    "transfer_identity_required",
    "plugin_unavailable",
]


class DestinationOutcome(Model):
    destination: str
    state: Literal["not_started", "complete", "failed", "remote_state_unconfirmed"] = (
        "not_started"
    )
    last_confirmed_stage: Stage = "not_started"
    diagnostic: Diagnostic | None = None
    pending_operation: Operation | None = None
    transfer: PushResult | None = None
    proof: DeliveryResult | None = None
    publication: PublishResult | None = None
    admission: AdmissionResult | None = None
    _destination = field_validator("destination")(PushRequest.reference.__func__)


class BatchResult(Model):
    schema_version: Literal["apizr.delivery-batch/v1"] = Field(
        default="apizr.delivery-batch/v1", alias="schema"
    )
    build: DeliveryManifest
    delivery_manifest_digest: Digest
    proof_requirement: ProofRequirement
    state: Literal["complete", "partial", "failed", "cancelled"]
    outcomes: tuple[DestinationOutcome, ...] = Field(
        min_length=1, max_length=MAX_DESTINATIONS
    )

    @property
    def exit_code(self) -> int:
        return (
            0 if self.state == "complete" else 130 if self.state == "cancelled" else 1
        )

    @model_validator(mode="after")
    def evidence_binding(self):
        if self.delivery_manifest_digest != identity(self.build):
            raise ValueError("Batch manifest mismatch")
        keys = [destination_key(o.destination) for o in self.outcomes]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate result destination")
        for outcome in self.outcomes:
            self._check_outcome(outcome)
        count = sum(o.state == "complete" for o in self.outcomes)
        expected = (
            "complete"
            if count == len(self.outcomes)
            else "partial"
            if count
            else "failed"
        )
        if self.state != "cancelled" and self.state != expected:
            raise ValueError("Aggregate state hides incomplete destinations")
        return self

    def _check_outcome(self, outcome: DestinationOutcome) -> None:
        push = outcome.transfer
        if push is None:
            if (
                outcome.last_confirmed_stage != "not_started"
                or any((outcome.proof, outcome.publication, outcome.admission))
                or outcome.state == "complete"
            ):
                raise ValueError("Missing transfer")
            return
        if (
            push.destination != outcome.destination
            or (push.image_id, push.platform, push.inputs_sha256)
            != (self.build.image_id, self.build.platform, self.build.inputs_sha256)
            or push.delivery_plan_digest != self.build.delivery_plan_digest
            or push.delivery_manifest_digest != self.delivery_manifest_digest
            or push.proof_requirement != self.proof_requirement
            or push.transfer_verified is not True
            or push.digest_reference
            != outcome.destination.rsplit(":", 1)[0] + "@" + push.manifest_digest
            or re.fullmatch(r"sha256:[0-9a-f]{64}", push.manifest_digest) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", push.config_digest) is None
            or push.image_id not in (push.config_digest, push.manifest_digest)
        ):
            raise ValueError("Transfer substitution")
        required_stage = {
            "proof_created": outcome.proof,
            "proof_published": outcome.publication,
            "admitted": outcome.admission,
        }
        if (
            outcome.last_confirmed_stage in required_stage
            and required_stage[outcome.last_confirmed_stage] is None
        ):
            raise ValueError("Unestablished stage")
        if self.proof_requirement == "optional" and any(
            (outcome.proof, outcome.publication, outcome.admission)
        ):
            raise ValueError("Optional push does not establish proof admission")
        proof = outcome.proof
        if proof is not None:
            if (
                proof.reference != push.digest_reference
                or proof.manifest_digest != push.manifest_digest
                or proof.delivery_plan_digest != push.delivery_plan_digest
                or proof.delivery_manifest_digest != push.delivery_manifest_digest
                or proof.checks
                != dict.fromkeys(
                    ("consistency", "recompute", "schema", "signature", "timestamp"),
                    "pass",
                )
                or any(
                    re.fullmatch(r"[0-9a-f]{64}", value) is None
                    for value in (proof.receipt_sha256, proof.signer)
                )
            ):
                raise ValueError("Proof substitution")
        publication = outcome.publication
        if publication is not None:
            if (
                proof is None
                or publication.verification != proof
                or publication.receipt_sha256 != proof.receipt_sha256
                or publication.image_reference != push.digest_reference
                or publication.image_digest != push.manifest_digest
            ):
                raise ValueError("Publication substitution")
            if publication.artifact_reference is not None:
                digest_reference(publication.artifact_reference)
                if publication.artifact_reference != outcome.destination.rsplit(":", 1)[
                    0
                ] + "@" + str(publication.artifact_manifest_digest):
                    raise ValueError("Cross-repository publication")
        admission = outcome.admission
        if admission is not None:
            digest_reference(admission.proof_artifact_reference)
            if (
                admission.destination != outcome.destination
                or admission.image_reference != push.digest_reference
                or admission.delivery_plan_digest != push.delivery_plan_digest
                or admission.delivery_manifest_digest != push.delivery_manifest_digest
                or admission.proof_artifact_reference
                != outcome.destination.rsplit(":", 1)[0]
                + "@"
                + admission.proof_artifact_manifest_digest
                or any(
                    re.fullmatch(r"[0-9a-f]{64}", value) is None
                    for value in (admission.receipt_sha256, admission.signer)
                )
                or (
                    proof is not None
                    and (admission.receipt_sha256, admission.signer)
                    != (proof.receipt_sha256, proof.signer)
                )
                or (
                    publication is not None
                    and publication.state == "verified"
                    and admission.proof_artifact_reference
                    != publication.artifact_reference
                )
            ):
                raise ValueError("Admission substitution")
        if outcome.state == "complete" and (
            outcome.diagnostic is not None
            or outcome.pending_operation is not None
            or (
                self.proof_requirement == "required"
                and (admission is None or admission.state != "admitted")
            )
            or (
                self.proof_requirement == "optional"
                and push.destination_promoted is not True
            )
        ):
            raise ValueError("Incomplete destination cannot be complete")
