"""Portable admission budgets for retained repository bundle artifacts."""

import os
import stat
from collections.abc import Collection, Mapping
from pathlib import Path, PurePosixPath

from apizr.contracts.json_budget import preflight_json
from apizr.interfaces.runtime import IntegrityError

MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_BUNDLE_BYTES = 512 * 1024 * 1024
MAX_BUNDLE_ARTIFACTS = 100_256
MAX_JSON_NODES = 1_000_000
MAX_JSON_DEPTH = 128


def artifact_limit(name: str) -> int:
    if name in ("apizr-repository-rest.json", "apizr-repository-mcp.json"):
        return MAX_MANIFEST_BYTES
    return MAX_ARTIFACT_BYTES


def check_artifact(name: str, content: bytes, limit: int) -> None:
    if len(content) > limit:
        raise IntegrityError("Repository artifact byte limit exceeded")
    # Application resources below source/ are opaque, even with a JSON suffix.
    if name.endswith(".json") and not name.startswith("source/"):
        preflight_json(
            content,
            max_bytes=limit,
            max_nodes=MAX_JSON_NODES,
            max_depth=MAX_JSON_DEPTH,
        )


def read_artifact(root: Path, name: str, limit: int | None = None) -> bytes:
    path = PurePosixPath(name)
    if (
        not path.parts
        or path.is_absolute()
        or str(path) != name
        or ".." in path.parts
        or "\\" in name
    ):
        raise IntegrityError("Invalid repository artifact")
    limit = artifact_limit(name) if limit is None else min(limit, artifact_limit(name))
    if limit < 0:
        raise IntegrityError("Repository artifact byte limit exceeded")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        file = os.open(
            path.parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=descriptor,
        )
        with os.fdopen(file, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise IntegrityError("Repository artifact must be a regular file")
            if metadata.st_size > limit:
                raise IntegrityError("Repository artifact byte limit exceeded")
            content = stream.read(limit + 1)
        check_artifact(name, content, limit)
        return content
    finally:
        os.close(descriptor)


class BundleBudget:
    """Charge the manifest and every retained artifact before the next read."""

    def __init__(self) -> None:
        self.size = 0
        self.count = 0

    def allowance(self, name: str) -> int:
        if self.count >= MAX_BUNDLE_ARTIFACTS:
            raise IntegrityError("Repository artifact count limit exceeded")
        return min(artifact_limit(name), MAX_BUNDLE_BYTES - self.size)

    def read(self, root: Path, name: str) -> bytes:
        content = read_artifact(root, name, self.allowance(name))
        self.size += len(content)
        self.count += 1
        return content

    def read_many(self, root: Path, names: Collection[str]) -> dict[str, bytes]:
        if len(names) + self.count > MAX_BUNDLE_ARTIFACTS:
            raise IntegrityError("Repository artifact count limit exceeded")
        return {name: self.read(root, name) for name in names}


def check_bundle(artifacts: Mapping[str, bytes]) -> None:
    """Refuse generation of a bundle that its readers cannot admit."""
    try:
        if len(artifacts) > MAX_BUNDLE_ARTIFACTS:
            raise IntegrityError("Repository artifact count limit exceeded")
        budget = BundleBudget()
        for name, content in artifacts.items():
            check_artifact(name, content, budget.allowance(name))
            budget.size += len(content)
            budget.count += 1
    except IntegrityError as error:
        raise ValueError(str(error)) from None
