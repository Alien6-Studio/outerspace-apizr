"""Versioned REST plan and artifact contract, separate from IR/readiness."""

from typing import Literal

from apizr.capabilities.model import Digest, Source
from apizr.capabilities.types import ValueModel
from apizr.interfaces.model import Input as Input
from apizr.interfaces.model import InvocationContract
from apizr.interfaces.model import Scalar as Scalar
from apizr.interfaces.model import TypeSpec as TypeSpec


class Endpoint(InvocationContract):
    route: str
    method: Literal["POST"] = "POST"


class RestPlan(ValueModel):
    schema_version: Literal["apizr.rest/v1"] = "apizr.rest/v1"
    source: Source
    executable_digest: Digest
    executable_path: str
    ir_digest: Digest
    readiness_digest: Digest
    endpoints: tuple[Endpoint, ...]


class Manifest(ValueModel):
    schema_version: Literal["apizr.rest/v1"] = "apizr.rest/v1"
    source: Source
    executable_digest: Digest
    executable_path: str
    ir_digest: Digest
    readiness_digest: Digest
    capabilities: tuple[Endpoint, ...]
    artifacts: dict[str, Digest]
