"""Shared immutable publication results; no plugin implementation dependencies."""

from typing import Literal

from pydantic import Field, model_validator

from apizr.capabilities.model import Digest
from apizr.contracts.delivery import (
    DeliveryManifest,
    DeliveryPlan,
    check_observation,
    identity,
)
from apizr.contracts.publication import Model


class BuildResult(Model):
    delivery_plan: DeliveryPlan | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    delivery_manifest: DeliveryManifest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    delivery_manifest_digest: Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def lineage(self):
        if self.delivery_manifest is None:
            if (
                self.delivery_plan is not None
                or self.delivery_manifest_digest is not None
            ):
                raise ValueError("Incomplete delivery lineage")
        else:
            if (
                self.delivery_plan is None
                or identity(self.delivery_plan)
                != self.delivery_manifest.delivery_plan_digest
                or identity(self.delivery_manifest) != self.delivery_manifest_digest
                or self.delivery_plan.platform != self.platform
            ):
                raise ValueError("Delivery lineage mismatch")
            check_observation(
                self.delivery_manifest, self.image_id, self.platform, self.inputs_sha256
            )
        return self

    schema_version: Literal["apizr.oci-build-result/v1"] = Field(
        default="apizr.oci-build-result/v1", alias="schema"
    )
    tag: str
    platform: str
    image_id: str
    inputs_sha256: str
    published: Literal[False] = False


class PushResult(Model):
    # Absent fields preserve historical image-publication semantics.
    proof_requirement: Literal["optional", "required"] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    transfer_verified: Literal[True] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    destination_promoted: bool | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    delivery_admitted: Literal[False] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )

    @model_validator(mode="after")
    def publication_state(self):
        states = (
            self.proof_requirement,
            self.transfer_verified,
            self.destination_promoted,
            self.delivery_admitted,
        )
        if any(v is not None for v in states):
            if any(v is None for v in states) or self.destination_promoted != (
                self.proof_requirement == "optional"
            ):
                raise ValueError("Inconsistent publication state")
            if (
                self.proof_requirement == "required"
                and self.delivery_manifest_digest is None
            ):
                raise ValueError("Required proof needs delivery lineage")
        return self

    delivery_plan_digest: Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    delivery_manifest_digest: Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def lineage(self):
        if (self.delivery_plan_digest is None) != (
            self.delivery_manifest_digest is None
        ):
            raise ValueError("Incomplete delivery lineage")
        return self

    schema_version: Literal["apizr.oci-push-result/v1"] = Field(
        default="apizr.oci-push-result/v1", alias="schema"
    )
    destination: str
    digest_reference: str
    platform: str
    image_id: str
    config_digest: str
    manifest_digest: str
    index_digest: None = None
    inputs_sha256: str
    published: Literal[True] = True


class VerifiedAttestTool(Model):
    version: Literal["0.1.0"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DeliveryResult(Model):
    delivery_plan_digest: Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    delivery_manifest_digest: Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    attest_tool: VerifiedAttestTool | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    schema_version: Literal["apizr.attest-delivery-result/v1"] = Field(
        default="apizr.attest-delivery-result/v1", alias="schema"
    )
    reference: str
    manifest_digest: str
    signer: str
    receipt_sha256: str
    checks: dict[str, Literal["pass"]]
    scope: Literal["verified OCI delivery; build not supervised by Attest"] = (
        "verified OCI delivery; build not supervised by Attest"
    )
    receipt_published: Literal[False] = False
    registry_availability_verified: Literal[False] = False


# Transport-only discovery deliberately has no Attest binary or trust inputs.


class PublishResult(Model):
    schema_version: Literal["apizr.published-proof/v1"] = Field(
        default="apizr.published-proof/v1", alias="schema"
    )
    image_reference: str
    image_digest: str
    artifact_reference: str | None = None
    artifact_manifest_digest: str | None = None
    receipt_sha256: str
    verification: DeliveryResult
    state: Literal["verified", "remote_state_unconfirmed"] = "verified"
    receipt_published: bool = True

    @model_validator(mode="after")
    def confirmation(self):
        if self.state == "verified":
            if (
                not self.receipt_published
                or self.artifact_reference is None
                or self.artifact_manifest_digest is None
            ):
                raise ValueError("verified publication requires artifact identities")
        elif (
            self.receipt_published
            or self.artifact_reference is not None
            or self.artifact_manifest_digest is not None
        ):
            raise ValueError("unconfirmed publication cannot claim remote identities")
        return self


class AdmissionResult(Model):
    schema_version: Literal["apizr.delivery-admission/v1"] = Field(
        default="apizr.delivery-admission/v1", alias="schema"
    )
    state: Literal["admitted", "remote_state_unconfirmed"] = "admitted"
    destination: str
    image_reference: str
    delivery_plan_digest: Digest
    delivery_manifest_digest: Digest
    proof_artifact_reference: str
    proof_artifact_manifest_digest: str
    receipt_sha256: str
    signer: str
    transfer_verified: Literal[True] = True
    destination_promoted: bool | None = True
    delivery_admitted: bool = True

    @model_validator(mode="after")
    def confirmation(self):
        if self.state == "admitted":
            if not self.delivery_admitted or self.destination_promoted is not True:
                raise ValueError("Admission requires verified promotion")
        elif self.delivery_admitted or self.destination_promoted is not None:
            raise ValueError("Unconfirmed promotion cannot claim admission")
        return self


class ObservedImage(Model):
    digest_reference: str
    config_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ObservationResult(Model):
    schema_version: Literal["apizr.delivery-observation/v1"] = Field(
        default="apizr.delivery-observation/v1", alias="schema"
    )
    destination: str
    state: Literal["verified", "absent", "conflict", "remote_state_unconfirmed"]
    image: ObservedImage | None = None
