"""Operator-selected configuration and descriptor-anchored repository scope."""

import json
import os
import stat
from pathlib import Path

from apizr.exposure import ExposurePolicy
from apizr.extension_runtime.protocol import unique_object
from apizr.project import load_project
from apizr.repository_readiness import RepositoryReadinessPolicy

from .model import Scope


def open_root(root: str) -> int:
    """Traverse every component without following links, retaining only one fd."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    path = Path(root)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("invalid_root")
    descriptor = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


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


def load_scope(path: Path) -> Scope:
    # The operator chooses this file, never the remote client. Refuse ordinary
    # special-file mistakes before calling the existing bounded TOML loader.
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("invalid_project_file")
    config = load_project(path)
    if config.root.is_symlink():
        raise ValueError("invalid_root")
    root = str(config.root.resolve(strict=True))
    descriptor = open_root(root)
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
        root=root,
        device=identity.st_dev,
        inode=identity.st_ino,
        scan=config.scan,
        graph=config.graph,
        readiness=readiness,
        exposure=exposure,
    )
