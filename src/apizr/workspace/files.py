"""Bounded regular files and descriptor-relative traversal for explicit inputs."""

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def absolute_path(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    # macOS system aliases, not arbitrary user-controlled symlinks.
    for prefix in (Path("/tmp"), Path("/var")):
        if path.is_relative_to(prefix) and prefix.is_symlink():
            path = prefix.resolve() / path.relative_to(prefix)
    return path


@contextmanager
def directory_fd(path: Path) -> Iterator[int]:
    path = absolute_path(path)
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def read_regular(path: Path, limit: int) -> bytes:
    path = absolute_path(path)
    with directory_fd(path.parent) as parent:
        descriptor = os.open(
            path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent
        )
        with os.fdopen(descriptor, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError("regular_file_required")
            data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("file_too_large")
    return data
