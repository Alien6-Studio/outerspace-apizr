"""Owned analysis scope passed across MCP exec and worker boundaries, without SDK imports."""

import json
import os
import stat
from pathlib import Path

from pydantic import ConfigDict

from apizr.analysis_contracts import PinnedRoot
from apizr.capabilities.types import ValueModel
from apizr.exposure import ExposurePolicy
from apizr.extension_runtime.protocol import unique_object
from apizr.graph import GraphPolicy
from apizr.operator_policy import OperatorPolicy
from apizr.repository import ScanPolicy
from apizr.repository_readiness import RepositoryReadinessPolicy
from apizr.source_access import open_analysis_root
from apizr.workspace.project import load_project

MAX_SESSION_BYTES = 1048576


class Scope(ValueModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    root: str
    device: int
    inode: int
    scan: ScanPolicy
    graph: GraphPolicy
    readiness: RepositoryReadinessPolicy
    exposure: ExposurePolicy | None
    operator_policy: OperatorPolicy | None

    def source(self) -> PinnedRoot:
        return PinnedRoot(root=self.root, device=self.device, inode=self.inode)


def check_scope(scope: Scope) -> None:
    """Recheck admission and inode before spawning a calculation (worker rechecks too)."""
    os.close(open_analysis_root(scope.source(), scope.operator_policy))


def read_session(descriptor: int) -> Scope:
    """Consume a private inherited descriptor once; no authority file is reopened."""
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("invalid_session")
        raw = stream.read(MAX_SESSION_BYTES + 1)
    if len(raw) > MAX_SESSION_BYTES:
        raise ValueError("session_too_large")
    scope = Scope.model_validate_json(raw, strict=True)
    check_scope(scope)
    return scope


def policy_bytes(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError("invalid_policy_file")
    with os.fdopen(descriptor, "rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("policy_too_large")
    # Preserve existing policy models, but reject duplicate JSON object keys.
    return json.dumps(
        json.loads(raw, object_pairs_hook=unique_object), allow_nan=False
    ).encode()


def load_scope(path: Path, operator_policy: OperatorPolicy | None = None) -> Scope:
    # The operator chooses this file, never the remote client. Refuse ordinary
    # special-file mistakes before calling the existing bounded TOML loader.
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("invalid_project_file")
    config = load_project(path)
    root = os.path.abspath(config.root)
    authority = (
        OperatorPolicy.model_validate_json(
            operator_policy.model_dump_json(), strict=True
        )
        if operator_policy is not None
        else None
    )
    descriptor = open_analysis_root(root, authority)
    try:
        identity = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    readiness = (
        RepositoryReadinessPolicy.model_validate_json(
            policy_bytes(config.readiness_policy), strict=True
        )
        if config.readiness_policy is not None
        else RepositoryReadinessPolicy()
    )
    exposure = (
        ExposurePolicy.model_validate_json(
            policy_bytes(config.exposure_policy), strict=True
        )
        if config.exposure_policy is not None
        else None
    )
    return Scope(
        operator_policy=authority,
        root=root,
        device=identity.st_dev,
        inode=identity.st_ino,
        scan=config.scan,
        graph=config.graph,
        readiness=readiness,
        exposure=exposure,
    )
