"""Portable, acyclic delivery identities; never operator authority or credentials."""

from importlib.metadata import version
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel
from apizr.distribution_identity import LockedDistribution, Version

PLAN_FILE = "apizr-delivery-plan.json"
MANIFEST_FILE = "apizr-delivery-manifest.json"
PLAN_LABEL = "sh.outerspace.apizr.delivery-plan-sha256"
PROOF_LABEL = "sh.outerspace.apizr.proof-requirement"
ProofRequirement = Literal["optional", "required"]

PROVENANCE_FILE = "apizr-bundle-provenance.json"


class LocalSource(ValueModel):
    kind: Literal["local"] = "local"
    repository_digest: Digest


class UnrecordedSource(ValueModel):
    """Historical/lower-level evidence has no established acquisition provenance."""

    kind: Literal["unrecorded"] = "unrecorded"
    repository_digest: Digest


class GitSource(ValueModel):
    kind: Literal["git"] = "git"
    repository: str
    requested_ref: str
    resolved_commit: str = Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    subdir: str
    repository_digest: Digest

    @field_validator("repository")
    @classmethod
    def repository_is_safe(cls, value: str) -> str:
        from apizr.git_source.contracts import is_ssh, validate_ssh_url, validate_url

        (validate_ssh_url if is_ssh(value) else validate_url)(value)
        return value

    @field_validator("requested_ref")
    @classmethod
    def explicit_reference(cls, value: str) -> str:
        from apizr.git_source.contracts import validate_ref

        validate_ref(value)
        return value

    @field_validator("subdir")
    @classmethod
    def relative_subdir(cls, value: str) -> str:
        from apizr.git_source.contracts import relative_path

        return relative_path(value).as_posix()


SourceIdentity = Annotated[
    LocalSource | GitSource | UnrecordedSource, Field(discriminator="kind")
]


class DistributionIdentity(ValueModel):
    """Installed metadata declaration, not a binary/distribution archive attestation."""

    name: Literal["outerspace-apizr", "outerspace-apizr-oci"]
    version: Version


def installed_identity(
    name: Literal["outerspace-apizr", "outerspace-apizr-oci"],
) -> DistributionIdentity:
    return DistributionIdentity(name=name, version=version(name))


class BundleProvenance(ValueModel):
    schema_version: Literal["apizr.bundle-provenance/v1"] = "apizr.bundle-provenance/v1"
    source: SourceIdentity
    generator: DistributionIdentity

    @model_validator(mode="after")
    def core_generator(self) -> Self:
        if self.generator.name != "outerspace-apizr":
            raise ValueError("Expected core generator identity")
        return self


class DeliveryPlan(ValueModel):
    # Omission preserves canonical identities of pre-gating plans.
    proof_requirement: ProofRequirement = Field(
        default="optional", exclude_if=lambda v: v == "optional"
    )
    schema_version: Literal["apizr.delivery-plan/v1"] = "apizr.delivery-plan/v1"
    source: SourceIdentity
    catalog_digest: Digest
    graph_digest: Digest
    scan_policy_digest: Digest
    graph_policy_digest: Digest
    readiness_policy_digest: Digest
    repository_readiness_digest: Digest
    exposure_policy_digest: Digest
    exposure_plan_digest: Digest
    repository_interface_digest: Digest
    application_inputs_digest: Digest | None = None
    bundle_manifest_digest: Digest
    interface: Literal["rest", "mcp"]
    dependency_closure: tuple[LockedDistribution, ...] = Field(
        min_length=1, max_length=128
    )
    generator: DistributionIdentity | None = None
    build_tools: tuple[DistributionIdentity, ...]
    platform: Literal["linux/amd64", "linux/arm64"]
    base_image: str = Field(
        pattern=r"^[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}$", max_length=512
    )

    @field_validator("dependency_closure")
    @classmethod
    def canonical_closure(
        cls, values: tuple[LockedDistribution, ...]
    ) -> tuple[LockedDistribution, ...]:
        if len({item.name for item in values}) != len(values):
            raise ValueError("Duplicate locked dependency")
        return tuple(sorted(values, key=lambda item: item.name))

    @field_validator("build_tools")
    @classmethod
    def exact_tools(
        cls, values: tuple[DistributionIdentity, ...]
    ) -> tuple[DistributionIdentity, ...]:
        if sorted(item.name for item in values) != [
            "outerspace-apizr",
            "outerspace-apizr-oci",
        ]:
            raise ValueError("Expected installed core and OCI identities")
        return tuple(sorted(values, key=lambda item: item.name))

    @model_validator(mode="after")
    def generator_is_core(self) -> Self:
        if self.generator is not None and self.generator.name != "outerspace-apizr":
            raise ValueError("Expected core generator identity")
        return self


class DeliveryManifest(ValueModel):
    """Observed build only: schema forbids destinations, receipts and proof identities."""

    schema_version: Literal["apizr.delivery-manifest/v1"] = "apizr.delivery-manifest/v1"
    delivery_plan_digest: Digest
    inputs_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    platform: Literal["linux/amd64", "linux/arm64"]
    image_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def identity(value: ValueModel) -> Digest:
    """Reuse the repository's canonical UTF-8 representation and Digest primitive."""
    from apizr.repository.serialization import canonical_bytes

    return Digest.of_bytes(canonical_bytes(value))


def check_observation(
    manifest: DeliveryManifest, image_id: str, platform: str, inputs_sha256: str
) -> None:
    if (manifest.image_id, manifest.platform, manifest.inputs_sha256) != (
        image_id,
        platform,
        inputs_sha256,
    ):
        raise ValueError("Delivery manifest and observed build disagree")
