"""Explicit operator grants for managed publication; decisions perform no I/O."""

import json
import os
import stat
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from apizr.execution.protocol import SizeExceeded, encode
from apizr.extension_runtime.protocol import unique_object
from apizr.local_plugins.models import (
    Digest,
    Installation,
    LockedDistribution,
    Version,
    canonical_name,
)
from apizr.publication_contracts import (
    Model,
    PublishRequest,
    PushRequest,
    digest_reference,
)

MAX_POLICY_BYTES = 65536
Permission = Literal["registry.read", "registry.publish"]
Code = Literal[
    "authorized",
    "not_required",
    "operator_policy_required",
    "operator_policy_invalid",
    "operator_policy_unavailable",
    "operator_policy_too_large",
    "operator_arguments_invalid",
    "operator_identity_denied",
    "operator_operation_denied",
    "operator_repository_denied",
    "operator_permissions_denied",
]


def repository_name(value: str) -> str:
    """An explicit repository only; preserve ports, normalize the documented Hub alias."""
    if len(value) > 255:
        raise ValueError("repository too long")
    PushRequest.reference(value + ":explicit")
    host, path = value.split("/", 1)
    return ("docker.io" if host == "index.docker.io" else host) + "/" + path


class PluginIdentity(Model):
    name: str
    version: Version
    sha256: Digest
    lock_sha256: Digest | None
    dependencies: tuple[LockedDistribution, ...] = Field(max_length=127)

    @field_validator("name")
    @classmethod
    def canonical(cls, value: str) -> str:
        if canonical_name(value) != value:
            raise ValueError("canonical plugin name required")
        return value

    @model_validator(mode="after")
    def closure(self) -> "PluginIdentity":
        if len({d.name for d in self.dependencies}) != len(self.dependencies):
            raise ValueError("duplicate dependency")
        if self.dependencies and self.lock_sha256 is None:
            raise ValueError("dependencies require a lock identity")
        return self

    @classmethod
    def from_installation(cls, record: Installation) -> "PluginIdentity":
        return cls(
            name=record.name,
            version=record.version,
            sha256=record.sha256,
            lock_sha256=record.lock_sha256,
            dependencies=tuple(sorted(record.dependencies, key=lambda d: d.name)),
        )

    @field_validator("dependencies")
    @classmethod
    def ordered(
        cls, value: tuple[LockedDistribution, ...]
    ) -> tuple[LockedDistribution, ...]:
        return tuple(sorted(value, key=lambda d: d.name))


class Grant(Model):
    plugin: PluginIdentity
    operation: Literal["push", "publish"]
    repository: str
    permissions: tuple[Permission, ...] = Field(min_length=1, max_length=2)

    _repository = field_validator("repository")(repository_name)

    @field_validator("permissions")
    @classmethod
    def unique(cls, value: tuple[Permission, ...]) -> tuple[Permission, ...]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate permission")
        return value


class OperatorPolicy(Model):
    schema_version: Literal["apizr.operator-policy/v1"] = Field(alias="schema")
    grants: tuple[Grant, ...] = Field(max_length=128)


class Decision(Model):
    schema_version: Literal["apizr.operator-decision/v1"] = Field(
        default="apizr.operator-decision/v1", alias="schema"
    )
    allowed: bool
    code: Code


class AuthorizationDenied(Exception):
    """Only a structured, fixed diagnostic; no paths, arguments or credentials."""

    def __init__(self, code: Code) -> None:
        self.decision = Decision(allowed=False, code=code)
        self.code = code
        super().__init__(code)


def load_operator_policy(path: Path) -> OperatorPolicy:
    """Read just the operator-selected bounded regular file, never discover one."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise AuthorizationDenied("operator_policy_invalid")
            raw = stream.read(MAX_POLICY_BYTES + 1)
        if len(raw) > MAX_POLICY_BYTES:
            raise AuthorizationDenied("operator_policy_too_large")
        json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        return OperatorPolicy.model_validate_json(raw, strict=True)
    except (ValueError, RecursionError):
        raise AuthorizationDenied("operator_policy_invalid") from None
    except OSError:
        raise AuthorizationDenied("operator_policy_unavailable") from None


# Trusted core knowledge, not supplied by a project, profile, catalog or plugin.
# Each operation reads the target repository both before and after publication.
OPERATIONS = {
    ("apizr-oci", "push"): "apizr_oci.protocol",
    ("apizr-attest", "publish"): "apizr_attest.protocol",
}


def decide(
    policy: OperatorPolicy | None,
    record: Installation,
    operation: str,
    arguments: dict[str, JsonValue],
) -> Decision:
    """Pure decision for an already validated installation and argument snapshot."""
    module = OPERATIONS.get((record.name, operation))
    # Also gate aliases of known official entry points; changing the manifest's
    # package name cannot turn the official publisher into an unchecked operation.
    known_module = any(
        op == operation and entry == record.module
        for (_, op), entry in OPERATIONS.items()
    )
    if module is None and not known_module:
        return Decision(allowed=True, code="not_required")
    if module != record.module:
        return Decision(allowed=False, code="operator_identity_denied")
    if policy is None:
        return Decision(allowed=False, code="operator_policy_required")
    try:
        # Revalidate typed API input too: model_construct/model_copy are not trust boundaries.
        policy = OperatorPolicy.model_validate_json(
            encode(policy.model_dump(mode="json", by_alias=True), MAX_POLICY_BYTES),
            strict=True,
        )
    except SizeExceeded:
        return Decision(allowed=False, code="operator_policy_too_large")
    except (ValueError, TypeError, AttributeError, RecursionError):
        return Decision(allowed=False, code="operator_policy_invalid")
    try:
        if operation == "push":
            request = PushRequest.model_validate(arguments, strict=True)
            repository = repository_name(request.destination.rsplit(":", 1)[0])
        else:
            proof = PublishRequest.model_validate(arguments, strict=True)
            repository = repository_name(
                digest_reference(proof.expected_reference).split("@")[0]
            )
        identity = PluginIdentity.from_installation(record)
    except (ValueError, TypeError, RecursionError):
        return Decision(allowed=False, code="operator_arguments_invalid")
    grants = [g for g in policy.grants if g.plugin == identity]
    if not grants:
        return Decision(allowed=False, code="operator_identity_denied")
    grants = [g for g in grants if g.operation == operation]
    if not grants:
        return Decision(allowed=False, code="operator_operation_denied")
    grants = [g for g in grants if g.repository == repository]
    if not grants:
        return Decision(allowed=False, code="operator_repository_denied")
    if not any(
        set(g.permissions) == {"registry.read", "registry.publish"} for g in grants
    ):
        return Decision(allowed=False, code="operator_permissions_denied")
    return Decision(allowed=True, code="authorized")
