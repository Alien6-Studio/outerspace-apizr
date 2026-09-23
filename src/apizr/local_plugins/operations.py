"""Install and enumerate verified local wheels without activating them."""

import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

from . import backend, locking, store
from .activation import active_inventory
from .models import Installation, Inventory, PluginError
from .wheel import inspect_wheel


def list_extensions(
    *, directory: Path | None = None, active: bool = False
) -> Inventory:
    """Read local records only. No uv, subprocess, import or network operation."""
    try:
        root = store.storage_directory(directory)
        return active_inventory(root) if active else store.read_inventory(root)
    except OSError:
        raise PluginError("inventory_unavailable") from None


def install_extension(
    wheel: Path,
    sha256: str,
    *,
    directory: Path | None = None,
    python: Path | None = None,
    requirements: Path | None = None,
    wheelhouse: Path | None = None,
) -> Installation:
    """Install one verified wheel offline; publication alone makes it visible."""
    locking.check_options(requirements, wheelhouse)
    lock = locking.read_lock(requirements) if requirements is not None else None
    uv = backend.require_uv()  # Before any filesystem modification, even a lock.
    python = python if python is not None else Path(sys.executable)
    if (
        not python.is_absolute()
        or not python.is_file()
        or not os.access(python, os.X_OK)
    ):
        raise PluginError("python_unavailable")
    data, manifest = inspect_wheel(wheel, sha256, allow_dependencies=lock is not None)
    try:
        root = store.storage_directory(directory)
        with store.installation_lock(root):
            inventory = store.read_inventory(root)
            for existing in inventory.installations:
                if (existing.name, existing.version) == (
                    manifest.name,
                    manifest.version,
                ):
                    if (
                        existing.sha256 != sha256.lower()
                        or existing.lock_sha256 != (lock.sha256 if lock else None)
                        or existing.dependencies
                        != (
                            [
                                item
                                for item in lock.packages
                                if item.name != manifest.name
                            ]
                            if lock
                            else []
                        )
                    ):
                        raise PluginError("installation_conflict")
                    if not Path(existing.python).is_file():
                        raise PluginError("installed_python_unavailable")
                    return existing
            if len(inventory.installations) >= 1000:
                raise PluginError("inventory_full")
            environments = root / "environments"
            store.private_directory(environments)
            identifier = uuid4().hex
            generation = environments / identifier
            generation.mkdir(mode=0o700)
            # This is the final path, not a venv that will later be relocated.
            interpreter = generation / "venv/bin/python"
            try:
                work = generation / "input"
                work.mkdir(mode=0o700)
                dependencies = []
                if lock is not None:
                    assert wheelhouse is not None
                    dependencies = locking.prepare(
                        lock, wheelhouse, manifest, sha256, data, wheel.name, work
                    )
                    dependency_options = [
                        "--find-links",
                        str(work / "wheels"),
                        "--strict",
                    ]
                else:
                    snapshot = work / wheel.name
                    snapshot.write_bytes(data)
                    (work / "requirements.txt").write_text(
                        f"{manifest.name} @ {snapshot.as_uri()} --hash=sha256:{sha256.lower()}\n",
                        encoding="utf-8",
                    )
                    dependency_options = ["--no-deps"]
                backend.run_uv(
                    uv,
                    [
                        "venv",
                        "--python",
                        str(python),
                        "--no-python-downloads",
                        "--no-project",
                        str(generation / "venv"),
                    ],
                    work,
                )
                backend.run_uv(
                    uv,
                    [
                        "pip",
                        "install",
                        "--python",
                        str(interpreter),
                        "--no-python-downloads",
                        "--no-index",
                        *dependency_options,
                        "--no-build",
                        "--no-sources",
                        "--require-hashes",
                        "--link-mode",
                        "copy",
                        "--requirements",
                        str(work / "requirements.txt"),
                    ],
                    work,
                )
                if not interpreter.is_file():
                    raise PluginError("uv_install_failed")
                if lock is not None:
                    locking.verify_installed(generation / "venv", lock)
                record = Installation.model_validate(
                    {
                        **manifest.model_dump(by_alias=True),
                        "sha256": sha256.lower(),
                        "environment_id": identifier,
                        "python": str(interpreter),
                        "lock_sha256": lock.sha256 if lock else None,
                        "dependencies": [item.model_dump() for item in dependencies],
                    }
                )
                # Discard installer scratch files before publishing, never after.
                shutil.rmtree(work)
                updated = Inventory(
                    installations=sorted(
                        [*inventory.installations, record],
                        key=lambda item: (item.name, item.version),
                    )
                )
                store.publish(root, updated)
                return record
            except BaseException:
                # A signal can arrive immediately after atomic publication. Keep
                # that fully installed environment if its record is already visible.
                try:
                    visible = any(
                        item.environment_id == identifier
                        for item in store.read_inventory(root).installations
                    )
                except (OSError, PluginError):
                    visible = True  # Unknown state: never risk breaking a record.
                if not visible:
                    shutil.rmtree(generation)
                raise
    except OSError:
        raise PluginError("installation_io_error") from None
