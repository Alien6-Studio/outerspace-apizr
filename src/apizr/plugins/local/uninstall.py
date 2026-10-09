"""Bounded exact-generation retirement and resumable, no-follow file removal."""

import os
import stat
import time
from pathlib import Path
from threading import Event
from typing import Literal

from pydantic import Field, TypeAdapter

from apizr.capabilities.types import ValueModel

from . import retirement, store, usage
from .activation import validated_activations
from .control import InstallationCancelled, InstallationTimeout, InstallControl
from .models import Installation, Inventory, PluginError, Version, canonical_name

MAX_ENTRIES = 100000
MAX_DEPTH = 64
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class UninstallDiagnostic(ValueModel):
    code: str


class UninstallResult(ValueModel):
    schema_version: Literal["apizr.plugin-uninstall/v1"] = "apizr.plugin-uninstall/v1"
    mode: Literal["dry-run", "apply"]
    state: Literal[
        "planned",
        "complete",
        "absent",
        "active",
        "busy",
        "refused",
        "incomplete",
        "interrupted",
        "unconfirmed",
    ] = "refused"
    exit_code: Literal[0, 1, 2, 130] = 2
    plugin: str | None = None
    version: Version | None = None
    target: Installation | None = None
    inventory_removed: bool = False
    environment_removed: bool = False
    cleanup_pending: bool = False
    effects: tuple[str, ...] = ()
    diagnostics: tuple[UninstallDiagnostic, ...] = ()


class UninstallLimits(ValueModel):
    timeout_ms: int = Field(default=30000, ge=1, le=600000, strict=True)


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _environment(root: Path, record: Installation) -> os.stat_result | None:
    parent = root / "environments"
    store.validate_directory(parent)
    try:
        info = (parent / record.environment_id).lstat()
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o022
    ):
        raise PluginError("unsafe_plugin_environment")
    return info


def _erase(
    parent: int,
    name: str,
    expected: tuple[int, int],
    control: InstallControl,
    count: list[int],
    depth: int = 0,
) -> None:
    """Walk directory descriptors; never follow even an internal symlink."""
    control.check()
    if depth > MAX_DEPTH:
        raise PluginError("cleanup_depth_limit")
    fd = os.open(name, DIRECTORY_FLAGS, dir_fd=parent)
    try:
        if _identity(os.fstat(fd)) != expected:
            raise PluginError("removal_identity_conflict")
        with os.scandir(fd) as entries:
            for entry in entries:
                control.check()
                count[0] += 1
                if count[0] > MAX_ENTRIES:
                    raise PluginError("cleanup_entry_limit")
                info = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    _erase(fd, entry.name, _identity(info), control, count, depth + 1)
                else:
                    os.unlink(entry.name, dir_fd=fd)
        control.check()
        if _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != expected:
            raise PluginError("removal_identity_conflict")
        os.rmdir(name, dir_fd=parent)
    finally:
        os.close(fd)


def _cleanup(root: Path, item: retirement.Retirement, control: InstallControl) -> None:
    info = _environment(root, item.installation)
    if info is None:
        return  # Previous attempt removed files but did not clear its intent.
    if _identity(info) != (item.device, item.inode):
        raise PluginError("removal_identity_conflict")
    fd = os.open(root / "environments", DIRECTORY_FLAGS)
    try:
        _erase(
            fd,
            item.installation.environment_id,
            (item.device, item.inode),
            control,
            [0],
        )
    finally:
        os.close(fd)


def uninstall_extension(
    name: str,
    version: str,
    *,
    directory: Path | None = None,
    dry_run: bool = False,
    timeout_ms: int = 30000,
    cancel: Event | None = None,
) -> UninstallResult:
    """Retire under the store lock, then erase with a persistent exact identity.

    Neither stage implies the other succeeded. Timeout/cancellation preserves the
    intent; another call for the same name/version resumes that generation only.
    """
    result = UninstallResult(mode="dry-run" if dry_run else "apply")
    root: Path | None = None
    attempted = False
    try:
        name = canonical_name(name)
        version = TypeAdapter[str](Version).validate_python(version, strict=True)
        limits = UninstallLimits(timeout_ms=timeout_ms)
        control = InstallControl(time.monotonic() + limits.timeout_ms / 1000, cancel)
        result = result.model_copy(update={"plugin": name, "version": version})
        control.check()
        root = store.storage_directory(directory)
        if not root.exists():
            return result.model_copy(update={"state": "absent", "exit_code": 0})
        store.validate_directory(root)
        lockfile = root / ".install.lock"
        if not lockfile.exists() and not lockfile.is_symlink():
            # An empty, pre-created store is still absent. Do not create it or
            # a lock during preview; an installer publishes only after its lock.
            if not any(
                p.exists() or p.is_symlink()
                for p in (
                    root / "installations.json",
                    root / "activations.json",
                    root / "removals.json",
                )
            ):
                return result.model_copy(update={"state": "absent", "exit_code": 0})
        with store.installation_lock(root, create=False, control=control):
            inventory = store.read_inventory(root, include_retiring=True)
            pending = retirement.read(root).pending
            active = validated_activations(root, inventory)
            selected = next(
                (
                    r
                    for r in inventory.installations
                    if (r.name, r.version) == (name, version)
                ),
                None,
            )
            intent = next(
                (
                    p
                    for p in pending
                    if (p.installation.name, p.installation.version) == (name, version)
                ),
                None,
            )
            record = intent.installation if intent else selected
            if record is None:
                return result.model_copy(update={"state": "absent", "exit_code": 0})
            result = result.model_copy(
                update={
                    "target": record,
                    "cleanup_pending": intent is not None,
                    "inventory_removed": selected is None,
                }
            )
            if record in active.activations:
                return result.model_copy(
                    update={
                        "state": "active",
                        "exit_code": 1,
                        "diagnostics": (UninstallDiagnostic(code="plugin_active"),),
                    }
                )
            info = _environment(root, record)
            if intent is None and info is None:
                raise PluginError("plugin_environment_missing")
            if (
                intent is not None
                and info is not None
                and _identity(info) != (intent.device, intent.inode)
            ):
                raise PluginError("removal_identity_conflict")
            with usage.lock(root, record, exclusive=True):
                control.check()
                if dry_run:
                    return result.model_copy(
                        update={
                            "state": "planned",
                            "exit_code": 0,
                            "effects": (
                                "remove_inventory_record",
                                "remove_dedicated_environment",
                            ),
                        }
                    )
                attempted = True
                if intent is None:
                    assert info is not None
                    intent = retirement.Retirement(
                        installation=record, device=info.st_dev, inode=info.st_ino
                    )
                    pending = [*pending, intent]
                    retirement.write(root, pending)
                # A pending intent also excludes this generation from admissions,
                # including a crash between intent publication and inventory removal.
                control.check()
                store.publish(
                    root,
                    Inventory(
                        installations=[
                            r for r in inventory.installations if r != record
                        ]
                    ),
                )
                result = result.model_copy(
                    update={
                        "inventory_removed": True,
                        "cleanup_pending": True,
                        "effects": ("remove_inventory_record",),
                    }
                )
                _cleanup(root, intent, control)
                control.check()
                retirement.write(root, [p for p in pending if p != intent])
                return result.model_copy(
                    update={
                        "state": "complete",
                        "exit_code": 0,
                        "environment_removed": True,
                        "cleanup_pending": False,
                        "effects": (
                            "remove_inventory_record",
                            "remove_dedicated_environment",
                        ),
                    }
                )
    except (KeyboardInterrupt, InstallationCancelled):
        code, state, exit_code = "uninstall_cancelled", "interrupted", 130
    except InstallationTimeout:
        code, state, exit_code = (
            "uninstall_timeout",
            "incomplete" if attempted else "refused",
            2,
        )
    except PluginError as error:
        code = str(error)
        state = (
            "busy"
            if code == "plugin_in_use"
            else "unconfirmed"
            if code == "plugin_usage_unconfirmed"
            else "incomplete"
            if attempted
            else "refused"
        )
        exit_code = 1 if state == "busy" else 2
    except (OSError, ValueError, RecursionError):
        code, state, exit_code = (
            "uninstall_input_or_io_error",
            "incomplete" if attempted else "refused",
            2,
        )
    if attempted and root is not None and result.target is not None:
        # An atomic write may have committed immediately before an interruption.
        # Report a bounded fresh observation, never infer rollback from an error.
        try:
            with store.installation_lock(
                root, create=False, control=InstallControl(time.monotonic() + 2)
            ):
                inventory = store.read_inventory(root, include_retiring=True)
                pending = retirement.read(root).pending
                info = _environment(root, result.target)
                gone = result.target not in inventory.installations
                result = result.model_copy(
                    update={
                        "inventory_removed": gone,
                        "environment_removed": info is None,
                        "cleanup_pending": any(
                            p.installation == result.target for p in pending
                        ),
                        "effects": (
                            *(["remove_inventory_record"] if gone else []),
                            *(["remove_dedicated_environment"] if info is None else []),
                        ),
                    }
                )
        except (OSError, PluginError, ValueError, KeyboardInterrupt):
            state = "unconfirmed"
    return result.model_copy(
        update={
            "state": state,
            "exit_code": exit_code,
            "diagnostics": (UninstallDiagnostic(code=code),),
        }
    )
