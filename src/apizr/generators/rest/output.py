"""Exclusive directory-descriptor writes; reject symlinks and existing output."""

import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath


def _directory(parent: int, name: str) -> int:
    try:
        os.mkdir(name, mode=0o755, dir_fd=parent)
    except FileExistsError:
        pass
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)


def write_bundle(output: str | Path, artifacts: Mapping[str, bytes]) -> None:
    if not os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
        raise OSError(
            "Safe REST output requires directory-descriptor/no-follow filesystem support"
        )
    path = Path(output)
    if ".." in path.parts:
        raise ValueError("Output path cannot contain parent traversal")
    for name in artifacts:
        entry = PurePosixPath(name)
        if (
            not entry.parts
            or entry.is_absolute()
            or ".." in entry.parts
            or str(entry) != name
            or "\\" in name
        ):
            raise ValueError("Artifact paths must be canonical relative paths")
    absolute = path.absolute()
    root = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            child = _directory(root, part)
            os.close(root)
            root = child
        if os.listdir(root):
            raise ValueError(
                "Output directory must be empty; no files were overwritten"
            )
        for name, content in sorted(artifacts.items()):
            parent = os.dup(root)
            try:
                parts = PurePosixPath(name).parts
                for part in parts[:-1]:
                    child = _directory(parent, part)
                    os.close(parent)
                    parent = child
                descriptor = os.open(
                    parts[-1],
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o644,
                    dir_fd=parent,
                )
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
            finally:
                os.close(parent)
    finally:
        os.close(root)
