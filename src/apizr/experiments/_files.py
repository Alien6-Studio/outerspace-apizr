"""Internal bounded regular-file observations, independent of evidence provenance."""

import hashlib
import os
import stat
from contextlib import ExitStack
from pathlib import Path
from typing import Literal

from apizr.workspace.files import directory_fd

_CHUNK_BYTES = 1024 * 1024
FileFailureCode = Literal["symlink", "not_regular", "too_large", "changed_during_read"]


class FileFailure(Exception):
    def __init__(self, code: FileFailureCode):
        self.code: FileFailureCode = code


def _snapshot(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def fingerprint_file(root: Path, reference: str, limit: int) -> tuple[str, int]:
    with ExitStack() as stack:
        parent = stack.enter_context(directory_fd(root))
        parts = reference.split("/")
        for index, part in enumerate(parts):
            info = os.stat(part, dir_fd=parent, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                raise FileFailure("symlink")
            if index < len(parts) - 1:
                if not stat.S_ISDIR(info.st_mode):
                    raise FileFailure("not_regular")
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
                )
                stack.callback(os.close, child)
                parent = child
            elif not stat.S_ISREG(info.st_mode):
                raise FileFailure("not_regular")
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
        stack.callback(os.close, descriptor)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise FileFailure("not_regular")
        if before.st_size > limit:
            raise FileFailure("too_large")
        digest = hashlib.sha256()
        size = 0
        while chunk := os.read(descriptor, min(_CHUNK_BYTES, limit - size + 1)):
            size += len(chunk)
            if size > limit:
                raise FileFailure("too_large")
            digest.update(chunk)
        after = os.fstat(descriptor)
        try:
            current = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        except OSError:
            current = None
        if (
            _snapshot(before) != _snapshot(after)
            or current is None
            or _snapshot(after) != _snapshot(current)
            or size != before.st_size
        ):
            raise FileFailure("changed_during_read")
        return digest.hexdigest(), size
