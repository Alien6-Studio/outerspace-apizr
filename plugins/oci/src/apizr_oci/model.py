"""Explicit, bounded inputs. No Docker command, shell or inherited credentials."""

from typing import Literal

from pydantic import Field, model_validator

from apizr.capabilities.model import Digest
from apizr.delivery import DeliveryManifest, DeliveryPlan, check_observation, identity
from apizr.publication_contracts import (
    Authentication as Authentication,
)
from apizr.publication_contracts import (
    BuildRequest as BuildRequest,
)
from apizr.publication_contracts import (
    Docker as Docker,
)
from apizr.publication_contracts import (
    Model as Model,
)
from apizr.publication_contracts import (
    PushRequest as PushRequest,
)


class BuildError(Exception):
    """Fixed diagnostic codes only; never expose Docker logs or argument values."""


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
