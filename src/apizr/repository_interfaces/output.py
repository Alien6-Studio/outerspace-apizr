"""Stage a complete bundle and atomically publish it without replacing contents."""

import os
import secrets
import shutil
import stat
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from apizr.interfaces.output import open_directory


def write_bundle(output: str | Path, artifacts: Mapping[str, bytes]) -> None:
    path = Path(output)
    if not path.name or ".." in path.parts:
        raise ValueError("Expected a fresh output directory")
    for name in artifacts:
        entry = PurePosixPath(name)
        if (
            not entry.parts
            or entry.is_absolute()
            or ".." in entry.parts
            or str(entry) != name
            or "\\" in name
        ):
            raise ValueError("Invalid artifact path")
    absolute = path.absolute()
    parent = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
    stage = ".apizr-stage-" + secrets.token_hex(16)
    staged = False
    try:
        for part in absolute.parts[1:-1]:
            child = open_directory(parent, part)
            os.close(parent)
            parent = child
        try:
            metadata = os.stat(absolute.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISDIR(metadata.st_mode):
                raise ValueError("Output must be a directory, not a link or file")
            target = os.open(
                absolute.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent,
            )
            try:
                if os.listdir(target):
                    raise ValueError("Output directory must be empty")
            finally:
                os.close(target)
        os.mkdir(stage, mode=0o700, dir_fd=parent)
        staged = True
        root = os.open(
            stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        try:
            for name, content in sorted(artifacts.items()):
                directory = os.dup(root)
                try:
                    parts = PurePosixPath(name).parts
                    for part in parts[:-1]:
                        child = open_directory(directory, part)
                        os.close(directory)
                        directory = child
                    file = os.open(
                        parts[-1],
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o644,
                        dir_fd=directory,
                    )
                    with os.fdopen(file, "wb") as stream:
                        stream.write(content)
                finally:
                    os.close(directory)
            os.fchmod(root, 0o755)
        finally:
            os.close(root)
        # POSIX directory rename cannot overwrite a nonempty directory or a link.
        os.rename(stage, absolute.name, src_dir_fd=parent, dst_dir_fd=parent)
        staged = False
    finally:
        if staged:
            shutil.rmtree(stage, dir_fd=parent)
        os.close(parent)
