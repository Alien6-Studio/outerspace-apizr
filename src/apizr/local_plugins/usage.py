"""Store-lock admission followed by a per-generation shared flock.

Always acquire the store lock before a usage lock; never wait for usage while
holding the store lock. Lock files have stable names and are never unlinked.
"""

import os
import stat
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from apizr.extension_runtime import CleanupFailed

from . import store
from .control import InstallControl
from .models import Installation, PluginError


@contextmanager
def lock(
    root: Path, record: Installation, *, exclusive: bool = False
) -> Generator[int | None]:
    """Called under the store lock. Exclusive checks never create files."""
    import fcntl

    directory = root / ".usage"
    if not directory.exists() and not directory.is_symlink():
        if exclusive:
            yield None
            return
        store.private_directory(directory)
    store.validate_directory(directory)
    marker = directory / (record.environment_id + ".unconfirmed")
    if marker.exists() or marker.is_symlink():
        raise PluginError("plugin_usage_unconfirmed")
    try:
        fd = os.open(
            directory / (record.environment_id + ".lock"),
            os.O_RDWR
            | os.O_NOFOLLOW
            | os.O_NONBLOCK
            | (0 if exclusive else os.O_CREAT),
            0o600,
        )
    except FileNotFoundError:
        if not exclusive:
            raise
        yield None
        return
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or info.st_mode & 0o022
        ):
            raise PluginError("invalid_usage_lock")
        try:
            fcntl.flock(
                fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB
            )
        except BlockingIOError:
            raise PluginError("plugin_in_use") from None
        yield fd
    finally:
        os.close(fd)


@contextmanager
def protect(
    record: Installation, root: Path, control: InstallControl | None = None
) -> Generator[int]:
    """Revalidate an exact snapshot and hold its lease through process cleanup."""
    with ExitStack() as stack:
        with store.installation_lock(root, create=False, control=control):
            if record not in store.read_inventory(root).installations:
                raise PluginError("installation_changed")
            fd = stack.enter_context(lock(root, record))
            assert fd is not None
        try:
            yield fd
        except CleanupFailed:
            # A failed supervisor cleanup must not turn an unknown live user into an
            # apparently idle generation. No automatic repair of this persistent guard.
            store.atomic_write(
                root / ".usage" / (record.environment_id + ".unconfirmed"),
                b"cleanup_unconfirmed\n",
            )
            raise
