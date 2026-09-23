"""Atomic, local-only installation inventory. Environments never move."""

import json
import os
import stat
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from apizr.extension_runtime.protocol import unique_object

from .models import Inventory, PluginError

MAX_INVENTORY_BYTES = 1024 * 1024


def storage_directory(directory: Path | None = None) -> Path:
    if os.name != "posix":
        raise PluginError("unsupported_platform")
    if directory is None:
        if sys.platform == "darwin":
            directory = Path.home() / "Library/Application Support/apizr/plugins"
        else:
            directory = (
                Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
                / "apizr/plugins"
            )
            if not directory.is_absolute():
                raise PluginError("invalid_plugins_directory")
    root = directory.absolute()
    # Reject symlinks, including ancestor indirection, rather than writing through
    # an unexpected core/project location. /tmp is a normal macOS system symlink,
    # so compare protected boundaries against the resolved path as well.
    resolved = root.resolve()
    if root.is_symlink():
        raise PluginError("invalid_plugins_directory")
    protected = {Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()}
    for start in (Path.cwd().resolve(), Path(__file__).resolve()):
        for parent in (start, *start.parents):
            if (parent / ".git").exists() or (parent / "pyproject.toml").is_file():
                protected.add(parent)
                break
    if any(
        resolved == path
        or resolved.is_relative_to(path)
        or path.is_relative_to(resolved)
        for path in protected
    ):
        raise PluginError("plugins_directory_overlaps_core_or_project")
    return resolved


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    validate_directory(path)


def validate_directory(path: Path) -> None:
    value = path.lstat()
    if (
        not stat.S_ISDIR(value.st_mode)
        or value.st_uid != os.getuid()
        or value.st_mode & 0o022
    ):
        raise PluginError("unsafe_plugins_directory")


@contextmanager
def installation_lock(root: Path, *, create: bool = True) -> Generator[None]:
    import fcntl

    if create:
        private_directory(root)
    else:
        validate_directory(root)
    descriptor = os.open(
        root / ".install.lock",
        os.O_RDWR | (os.O_CREAT if create else 0) | os.O_NOFOLLOW,
        0o600,
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise PluginError("invalid_installation_lock")
        deadline = time.monotonic() + 30
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PluginError("installation_busy") from None
                time.sleep(0.05)
        yield
    finally:
        os.close(descriptor)


def read_inventory(root: Path) -> Inventory:
    path = root / "installations.json"
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return Inventory()
    try:
        with os.fdopen(descriptor, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise PluginError("invalid_inventory")
            raw = source.read(MAX_INVENTORY_BYTES + 1)
        if len(raw) > MAX_INVENTORY_BYTES:
            raise PluginError("invalid_inventory")
        result = Inventory.model_validate(
            json.loads(raw, object_pairs_hook=unique_object), strict=True
        )
        identities: set[tuple[str, str]] = set()
        for item in result.installations:
            identity = (item.name, item.version)
            if identity in identities or item.python != str(
                root / "environments" / item.environment_id / "venv/bin/python"
            ):
                raise PluginError("invalid_inventory")
            identities.add(identity)
        return result
    except (ValueError, RecursionError):
        raise PluginError("invalid_inventory") from None


def publish(root: Path, inventory: Inventory) -> None:
    raw = inventory.model_dump_json(by_alias=True).encode() + b"\n"
    if len(raw) > MAX_INVENTORY_BYTES:
        raise PluginError("inventory_full")
    atomic_write(root / "installations.json", raw)


def atomic_write(path: Path, raw: bytes) -> None:
    root = path.parent
    temporary = root / (".inventory-" + uuid4().hex)
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            target.write(raw)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        # Atomic visibility is the commit point. Nothing fallible follows it:
        # interruption must never delete an environment already in the inventory.
    finally:
        temporary.unlink(missing_ok=True)
