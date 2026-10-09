"""Capture only explicit files after independent repository-analysis admission."""

import os
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from apizr.contracts.application import (
    MAX_APPLICATION_BYTES,
    MAX_RESOURCE_BYTES,
    ApplicationConfig,
)
from apizr.repository.discovery import Budget, ScanLimit, read_source
from apizr.repository.policy import ScanPolicy
from apizr.workspace.source_access import RepositoryInput, open_analysis_root

if TYPE_CHECKING:
    from apizr.workspace.operator_policy import OperatorPolicy


def capture_resources(
    root: RepositoryInput,
    config: ApplicationConfig,
    operator_policy: "OperatorPolicy | None",
) -> dict[str, bytes]:
    config = ApplicationConfig.model_validate(config.model_dump())
    if not config.resources:
        return {}
    anchor = open_analysis_root(root, operator_policy)
    policy = ScanPolicy(
        max_file_bytes=MAX_RESOURCE_BYTES, max_total_bytes=MAX_APPLICATION_BYTES
    )
    budget = Budget(policy)
    resources: dict[str, bytes] = {}
    identities: set[tuple[int, int]] = set()
    try:
        for path in config.resources:
            parent = os.dup(anchor)
            try:
                parts = PurePosixPath(path).parts
                for part in parts[:-1]:
                    child = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=parent,
                    )
                    os.close(parent)
                    parent = child
                identity = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
                key = (identity.st_dev, identity.st_ino)
                if key in identities:
                    raise ValueError("Duplicate application resource file identity")
                identities.add(key)
                source, diagnostic = read_source(
                    parent, parts[-1], path, policy, budget
                )
                if diagnostic is not None or source.content is None:
                    raise ValueError("Application resource exceeds size limit")
                resources[path] = source.content
            finally:
                os.close(parent)
    except ScanLimit:
        raise ValueError("Application resources exceed aggregate size limit") from None
    finally:
        os.close(anchor)
    return resources
