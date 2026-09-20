"""Canonical artifacts have external digests, never runtime metadata."""

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel
from apizr.interfaces.serialization import json_bytes


def canonical_bytes(model: ValueModel) -> bytes:
    return json_bytes(model.model_dump(mode="json"))


def digest(model: ValueModel) -> Digest:
    return Digest.of_bytes(canonical_bytes(model))


policy_bytes = canonical_bytes
policy_digest = digest
plan_bytes = canonical_bytes
plan_digest = digest
