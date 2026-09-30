"""Descriptor-relative staging and recoverable replacement of fully owned trees."""

import hashlib
import os
import shutil
import stat
from pathlib import Path

from apizr.config_files import absolute_path, directory_fd
from apizr.interfaces.serialization import json_bytes

from .model import (
    MANIFEST,
    MAX_FILE,
    MAX_FILES,
    MAX_TOTAL,
    ClientCollection,
    ClientError,
    ClientExportManifest,
    ClientExportResult,
    Format,
    logical_path,
    unique_json,
)
from .planner import plan_client_collection
from .renderers import IR_FILE, render_client_collection


def _tree(root: int) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    entries = 0
    total = 0

    def walk(parent: int, prefix: str = "") -> None:
        nonlocal entries, total
        for name in sorted(os.listdir(parent)):
            path = prefix + name
            logical_path(path)
            entries += 1
            if entries > MAX_FILES + 32:
                raise ClientError("client_collection_too_large")
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
                )
                try:
                    if not os.listdir(child):
                        raise ClientError("client_sync_conflict")
                    walk(child, path + "/")
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                fd = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
                )
                with os.fdopen(fd, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise ClientError("client_sync_conflict")
                    data = stream.read(MAX_FILE + 1)
                total += len(data)
                if len(data) > MAX_FILE or total > MAX_TOTAL:
                    raise ClientError("client_collection_too_large")
                files[path] = data
            else:
                raise ClientError("client_sync_conflict")

    walk(root)
    return files


def _owned(files: dict[str, bytes], format: Format) -> None:
    try:
        manifest = ClientExportManifest.model_validate_json(
            json_bytes(unique_json(files[MANIFEST])), strict=True
        )
        if manifest.format != format:
            raise ClientError("client_sync_conflict")
        expected = {f.path for f in manifest.files} | {MANIFEST}
        if set(files) != expected:
            raise ClientError("client_sync_conflict")
        from apizr.capabilities.model import Digest

        if any(Digest.of_bytes(files[f.path]) != f.digest for f in manifest.files):
            raise ClientError("client_export_modified")
        collection = ClientCollection.model_validate_json(
            json_bytes(unique_json(files[IR_FILE])), strict=True
        )
        # Verify ownership metadata against the canonical retained IR as well.
        if render_client_collection(collection, format=format) != files:
            raise ClientError("client_export_modified")
    except ClientError:
        raise
    except (KeyError, ValueError, TypeError, RecursionError):
        raise ClientError("client_export_invalid") from None


def _write(root: int, files: dict[str, bytes]) -> None:
    for path, content in sorted(
        files.items(), key=lambda item: (item[0] == MANIFEST, item[0])
    ):
        parent = os.dup(root)
        try:
            parts = path.split("/")
            for part in parts[:-1]:
                try:
                    os.mkdir(part, dir_fd=parent)
                except FileExistsError:
                    pass
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
                )
                os.close(parent)
                parent = child
            fd = os.open(
                parts[-1],
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o644,
                dir_fd=parent,
            )
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(parent)
        finally:
            os.close(parent)
    os.fsync(root)


def publish_collection(
    collection: ClientCollection,
    *,
    format: Format,
    output_dir: str | Path,
    sync: bool = False,
) -> ClientExportResult:
    files = render_client_collection(collection, format=format)
    path = absolute_path(Path(output_dir))
    if not path.name or ".." in Path(output_dir).parts:
        raise ClientError("client_sync_conflict")
    try:
        # Parents must already exist; never create unrelated directory trees.
        with directory_fd(path.parent) as parent:
            _publish(parent, path.name, files, format, sync)
    except ClientError:
        raise
    except (OSError, ValueError, RecursionError):
        raise ClientError("client_sync_conflict") from None
    manifest = ClientExportManifest.model_validate_json(files[MANIFEST])
    return ClientExportResult(
        state="synced" if sync else "exported",
        format=format,
        client_collection_digest=manifest.client_collection_digest,
        source_manifest_digest=manifest.source_manifest_digest,
        files=manifest.files,
    )


def _publish(
    parent: int, name: str, files: dict[str, bytes], format: Format, sync: bool
) -> None:
    stem = ".apizr-clients-" + hashlib.sha256(name.encode()).hexdigest()[:20]
    stage, backup, lock = stem + ".stage", stem + ".backup", stem + ".lock"
    # A leftover stage/backup/lock explicitly refuses: never guess after a crash.
    if any(p in os.listdir(parent) for p in (stage, backup, lock)):
        raise ClientError("client_sync_conflict")
    lock_fd = os.open(
        lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent
    )
    staged = False
    moved = False
    try:
        existing = name in os.listdir(parent)
        old: dict[str, bytes] = {}
        old_stat = None
        if existing:
            root = os.open(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
            )
            try:
                old_stat = os.fstat(root)
                if sync:
                    old = _tree(root)
                    _owned(old, format)
                elif os.listdir(root):
                    raise ClientError("client_output_not_empty")
            finally:
                os.close(root)
        elif sync:
            raise ClientError("client_export_invalid")
        os.mkdir(stage, mode=0o755, dir_fd=parent)
        staged = True
        root = os.open(
            stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        try:
            _write(root, files)
            if _tree(root) != files:
                raise ClientError("client_export_invalid")
        finally:
            os.close(root)
        if existing:
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if old_stat is None or (current.st_dev, current.st_ino) != (
                old_stat.st_dev,
                old_stat.st_ino,
            ):
                raise ClientError("client_sync_conflict")
            os.rename(name, backup, src_dir_fd=parent, dst_dir_fd=parent)
            moved = True
            root = os.open(
                backup, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
            )
            try:
                if _tree(root) != old:
                    raise ClientError("client_export_modified")
            finally:
                os.close(root)
        elif name in os.listdir(parent):
            raise ClientError("client_sync_conflict")
        os.rename(stage, name, src_dir_fd=parent, dst_dir_fd=parent)
        staged = False
        os.fsync(parent)
        if moved:
            shutil.rmtree(backup, dir_fd=parent)
            moved = False
    except BaseException:
        if moved and staged and name not in os.listdir(parent):
            os.rename(backup, name, src_dir_fd=parent, dst_dir_fd=parent)
            moved = False
        raise
    finally:
        os.close(lock_fd)
        if staged:
            shutil.rmtree(stage, dir_fd=parent)
        os.unlink(lock, dir_fd=parent)


def export_client_collection(
    bundle: str | Path,
    *,
    format: Format,
    output_dir: str | Path,
    base_url: str = "http://127.0.0.1:8000",
    name: str = "Apizr REST API",
    sync: bool = False,
) -> ClientExportResult:
    return publish_collection(
        plan_client_collection(bundle, name=name, base_url=base_url),
        format=format,
        output_dir=output_dir,
        sync=sync,
    )
