"""Explicit operator grants for Git, build, signing and publication; decisions perform no I/O."""

import json
import os
import stat
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, JsonValue, field_validator, model_validator

from apizr.analysis_contracts import AnalysisTarget, GitAnalysisTarget, LocalTarget
from apizr.bounded_json import MAX_REQUEST_BYTES, SizeExceeded, encode
from apizr.extension_runtime.protocol import unique_object
from apizr.git_source.contracts import GitTarget
from apizr.local_plugins.models import (
    Digest,
    Installation,
    LockedDistribution,
    Version,
    canonical_name,
)
from apizr.publication_contracts import (
    AttestRequest,
    BuildRequest,
    BuildTarget,
    Docker,
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
    "operator_key_denied",
    "operator_tsa_denied",
    "operator_build_denied",
    "operator_git_source_denied",
    "operator_analysis_denied",
    "operator_source_invalid",
    "operator_source_unavailable",
    "operator_source_changed",
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


def tsa_identity(value: str) -> tuple[str, str, int, str]:
    """Compare the explicit authority; no DNS, URL decoding or redirect discovery."""
    AttestRequest.tsa(value)
    url = urlsplit(value)
    if (
        len(value) > 2048
        or any(ord(c) < 33 or ord(c) == 127 for c in value)
        or "\\" in value
        or url.hostname is None
        or "%" in url.hostname
        or (url.port is not None and url.port < 1)
    ):
        raise ValueError("invalid timestamp authority")
    return (
        url.scheme,
        url.hostname,
        url.port or (443 if url.scheme == "https" else 80),
        url.path or "/",
    )


class SigningGrant(Model):
    plugin: PluginIdentity
    operation: Literal["attest"]
    repository: str
    key_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    expected_signer: Digest
    key_file: str
    tsa_url: str
    permissions: tuple[
        Literal["registry.read", "receipt.sign", "timestamp.request"], ...
    ] = Field(min_length=1, max_length=3)

    _repository = field_validator("repository")(repository_name)

    @field_validator("key_file")
    @classmethod
    def key_reference(cls, value: str) -> str:
        return Docker.absolute(value)

    @field_validator("tsa_url")
    @classmethod
    def authority(cls, value: str) -> str:
        tsa_identity(value)
        return value

    @field_validator("permissions")
    @classmethod
    def unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate permission")
        return value


class BuildGrant(Model):
    plugin: PluginIdentity
    operation: Literal["build"]
    target: BuildTarget
    permissions: tuple[Literal["image.build", "registry.read"], ...] = Field(
        min_length=1, max_length=2
    )

    @field_validator("permissions")
    @classmethod
    def unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate permission")
        return value


class GitGrant(Model):
    adapter: Literal["git"]
    operation: Literal["fetch"]
    target: GitTarget
    permissions: tuple[Literal["git.fetch"], ...] = Field(max_length=1)


class AnalysisGrant(Model):
    adapter: Literal["repository"]
    operation: Literal["analyze"]
    target: AnalysisTarget
    permissions: tuple[Literal["source.analyze"], ...] = Field(max_length=1)


class OperatorPolicy(Model):
    model_config = ConfigDict(serialize_by_alias=True)
    schema_version: Literal["apizr.operator-policy/v1"] = Field(alias="schema")
    grants: tuple[
        Annotated[
            Grant | SigningGrant | BuildGrant | GitGrant | AnalysisGrant,
            Field(discriminator="operation"),
        ],
        ...,
    ] = Field(max_length=128)


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
# Trusted effects: publication reads and writes; signing reads, signs and timestamps.
OPERATIONS = {
    # Existing local installations keep their exact identity and grants.
    ("apizr-oci", "build"): "apizr_oci.protocol",
    ("apizr-oci", "push"): "apizr_oci.protocol",
    ("apizr-attest", "publish"): "apizr_attest.protocol",
    ("apizr-attest", "attest"): "apizr_attest.protocol",
    ("outerspace-apizr-oci", "build"): "apizr_oci.protocol",
    ("outerspace-apizr-oci", "push"): "apizr_oci.protocol",
    ("outerspace-apizr-attest", "publish"): "apizr_attest.protocol",
    ("outerspace-apizr-attest", "attest"): "apizr_attest.protocol",
}


def decide(
    policy: OperatorPolicy | None,
    record: Installation,
    operation: str,
    arguments: dict[str, JsonValue],
) -> Decision:
    """Pure decision for an already validated installation and argument snapshot."""
    try:
        record = Installation.model_validate_json(
            encode(
                record.model_dump(mode="json", by_alias=True, warnings=False),
                MAX_POLICY_BYTES,
            ),
            strict=True,
        )
    except (ValueError, TypeError, AttributeError, RecursionError, SizeExceeded):
        return Decision(allowed=False, code="operator_identity_denied")
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
        policy = _validated_policy(policy)
    except AuthorizationDenied as error:
        return error.decision
    building: BuildTarget | None = None
    repository: str | None = None
    signing: AttestRequest | None = None
    authority: tuple[str, str, int, str] | None = None
    try:
        raw_arguments = encode(arguments, MAX_REQUEST_BYTES)
        if operation == "build":
            build = BuildRequest.model_validate_json(raw_arguments, strict=True)
            building = BuildTarget.model_validate(
                build.model_dump(include=set(BuildTarget.model_fields)), strict=True
            )
        elif operation == "push":
            request = PushRequest.model_validate_json(raw_arguments, strict=True)
            repository = repository_name(request.destination.rsplit(":", 1)[0])
        elif operation == "attest":
            signing = AttestRequest.model_validate_json(raw_arguments, strict=True)
            repository = repository_name(
                digest_reference(signing.expected_reference).split("@")[0]
            )
            authority = tsa_identity(signing.tsa_url)
        else:
            proof = PublishRequest.model_validate_json(raw_arguments, strict=True)
            repository = repository_name(
                digest_reference(proof.expected_reference).split("@")[0]
            )
        identity = PluginIdentity.from_installation(record)
    except (ValueError, TypeError, RecursionError, SizeExceeded):
        return Decision(allowed=False, code="operator_arguments_invalid")
    grants = [
        g
        for g in policy.grants
        if not isinstance(g, (GitGrant, AnalysisGrant)) and g.plugin == identity
    ]
    if not grants:
        return Decision(allowed=False, code="operator_identity_denied")
    grants = [g for g in grants if g.operation == operation]
    if not grants:
        return Decision(allowed=False, code="operator_operation_denied")
    if building is not None:
        builds = [
            g for g in grants if isinstance(g, BuildGrant) and g.target == building
        ]
        if not builds:
            return Decision(allowed=False, code="operator_build_denied")
        allowed = any(
            set(g.permissions) == {"image.build", "registry.read"} for g in builds
        )
        return Decision(
            allowed=allowed,
            code="authorized" if allowed else "operator_permissions_denied",
        )
    grants = [
        g
        for g in grants
        if not isinstance(g, BuildGrant) and g.repository == repository
    ]
    if not grants:
        return Decision(allowed=False, code="operator_repository_denied")
    if signing is not None:
        signing_grants = [
            g
            for g in grants
            if isinstance(g, SigningGrant)
            and (g.key_id, g.expected_signer, g.key_file)
            == (signing.key_id, signing.expected_signer, signing.key_file)
        ]
        if not signing_grants:
            return Decision(allowed=False, code="operator_key_denied")
        signing_grants = [
            g for g in signing_grants if tsa_identity(g.tsa_url) == authority
        ]
        if not signing_grants:
            return Decision(allowed=False, code="operator_tsa_denied")
        allowed = any(
            set(g.permissions) == {"registry.read", "receipt.sign", "timestamp.request"}
            for g in signing_grants
        )
        return Decision(
            allowed=allowed,
            code="authorized" if allowed else "operator_permissions_denied",
        )
    if not any(
        set(g.permissions) == {"registry.read", "registry.publish"} for g in grants
    ):
        return Decision(allowed=False, code="operator_permissions_denied")
    return Decision(allowed=True, code="authorized")


def _validated_policy(policy: OperatorPolicy) -> OperatorPolicy:
    try:
        # Revalidate typed API input too: model_construct/model_copy are not trust boundaries.
        return OperatorPolicy.model_validate_json(
            encode(
                policy.model_dump(mode="json", by_alias=True, warnings=False),
                MAX_POLICY_BYTES,
            ),
            strict=True,
        )
    except SizeExceeded:
        raise AuthorizationDenied("operator_policy_too_large") from None
    except (ValueError, TypeError, AttributeError, RecursionError):
        raise AuthorizationDenied("operator_policy_invalid") from None


def decide_git(policy: OperatorPolicy | None, target: GitTarget) -> Decision:
    """Pure exact source grant; Git is a core adapter, not an installed plugin."""
    if policy is None:
        return Decision(allowed=False, code="operator_policy_required")
    try:
        policy = _validated_policy(policy)
    except AuthorizationDenied as error:
        return error.decision
    try:
        target = GitTarget.model_validate_json(
            encode(target.model_dump(mode="json", warnings=False), MAX_POLICY_BYTES),
            strict=True,
        )
    except (ValueError, TypeError, AttributeError, RecursionError, SizeExceeded):
        return Decision(allowed=False, code="operator_arguments_invalid")
    grants = [g for g in policy.grants if isinstance(g, GitGrant)]
    if not grants:
        return Decision(allowed=False, code="operator_operation_denied")
    grants = [g for g in grants if g.target == target]
    if not grants:
        return Decision(allowed=False, code="operator_git_source_denied")
    if not any(g.permissions == ("git.fetch",) for g in grants):
        return Decision(allowed=False, code="operator_permissions_denied")
    return Decision(allowed=True, code="authorized")


def decide_analysis(
    policy: OperatorPolicy | None, target: LocalTarget | GitAnalysisTarget
) -> Decision:
    """Pure source admission; data supplied in memory is outside filesystem admission."""
    if policy is None:
        return Decision(allowed=False, code="operator_policy_required")
    try:
        policy = _validated_policy(policy)
    except AuthorizationDenied as error:
        return error.decision
    try:
        from pydantic import TypeAdapter

        target = TypeAdapter[LocalTarget | GitAnalysisTarget](
            AnalysisTarget
        ).validate_json(
            encode(target.model_dump(mode="json", warnings=False), MAX_POLICY_BYTES),
            strict=True,
        )
    except (ValueError, TypeError, AttributeError, RecursionError, SizeExceeded):
        return Decision(allowed=False, code="operator_source_invalid")
    grants = [g for g in policy.grants if isinstance(g, AnalysisGrant)]
    if not grants:
        return Decision(allowed=False, code="operator_operation_denied")
    grants = [g for g in grants if g.target == target]
    if not grants:
        return Decision(allowed=False, code="operator_analysis_denied")
    if not any(g.permissions == ("source.analyze",) for g in grants):
        return Decision(allowed=False, code="operator_permissions_denied")
    return Decision(allowed=True, code="authorized")
