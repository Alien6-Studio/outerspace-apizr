"""Explicit, bounded inputs. No Docker command, shell or inherited credentials."""

from typing import Literal

from pydantic import Field

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
    schema_version: Literal["apizr.oci-build-result/v1"] = Field(
        default="apizr.oci-build-result/v1", alias="schema"
    )
    tag: str
    platform: str
    image_id: str
    inputs_sha256: str
    published: Literal[False] = False


class PushResult(Model):
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
