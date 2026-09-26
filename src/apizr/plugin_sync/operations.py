"""Validate once, plan all conflicts, then install additively with bounded work."""

import time
from pathlib import Path
from threading import Event
from typing import Literal

from apizr.local_plugins import activation, backend, store
from apizr.local_plugins.control import InstallationCancelled, InstallControl
from apizr.local_plugins.models import Installation, Inventory, PluginError
from apizr.local_plugins.operations import install_extension
from apizr.plugin_lock.models import Diagnostic, LockError, Plugin
from apizr.plugin_lock.operations import installation_matches, prepared_lock

from .models import PluginAction, SyncLimits, SyncResult
from .probe import verify_interpreter


def _state(
    root: Path, control: InstallControl
) -> tuple[Inventory, activation.Activations]:
    control.check()
    if root.exists():
        store.validate_directory(root)
    if not any(
        path.exists() or path.is_symlink()
        for path in (root / "installations.json", root / "activations.json")
    ):
        return Inventory(), activation.Activations()
    with store.installation_lock(root, create=False, control=control):
        inventory, active = store.read_inventory(root), activation._read(root)
        for record in active.activations:
            activation._validate_binding(record, inventory)
        return inventory, active


def _record(plugin: Plugin, inventory: Inventory) -> Installation | None:
    return next(
        (
            item
            for item in inventory.installations
            if (item.name, item.version) == (plugin.wheel.name, plugin.wheel.version)
        ),
        None,
    )


def sync_plugins(
    project: Path,
    lock_path: Path,
    wheelhouse: Path,
    *,
    dry_run: bool = False,
    directory: Path | None = None,
    timeout_ms: int = 120000,
    cancel: Event | None = None,
) -> SyncResult:
    """Return partial progress; never discard a published installation on failure.

    Cleanup/reconciliation has a separate bounded grace after the total deadline.
    SIGKILL and uninterruptible OS calls cannot guarantee a final report.
    """
    mode: Literal["dry-run", "apply"] = "dry-run" if dry_run else "apply"
    result = SyncResult(mode=mode, state="refused", exit_code=2)
    actions: list[PluginAction] = []
    plugins: tuple[Plugin, ...] = ()
    root: Path | None = None
    current: str | None = None
    applying = False
    try:
        limits = SyncLimits(timeout_ms=timeout_ms)
        control = InstallControl(time.monotonic() + limits.timeout_ms / 1000, cancel)
        with prepared_lock(project, lock_path, wheelhouse, control.check) as prepared:
            plugins = prepared.lock.plugins
            result = result.model_copy(
                update={
                    "lock_sha256": prepared.result.lock_sha256,
                    "target": prepared.lock.target,
                }
            )
            if not prepared.result.valid:
                return result.model_copy(
                    update={
                        "exit_code": 1,
                        "diagnostics": prepared.result.diagnostics,
                        "plugins": tuple(
                            PluginAction(
                                name=p.wheel.name,
                                version=p.wheel.version,
                                action="refuse",
                                status="refused",
                            )
                            for p in plugins
                        ),
                    }
                )
            root = store.storage_directory(directory)
            inventory, active = _state(root, control)
            diagnostics: list[Diagnostic] = []
            for plugin in plugins:
                record = _record(plugin, inventory)
                conflict = record is not None and not installation_matches(
                    plugin, record
                )
                actions.append(
                    PluginAction(
                        name=plugin.wheel.name,
                        version=plugin.wheel.version,
                        action="refuse"
                        if conflict
                        else "reuse"
                        if record
                        else "install",
                        status="refused" if conflict else "not_attempted",
                        active=record is not None and record in active.activations,
                    )
                )
                if conflict:
                    diagnostics.append(
                        Diagnostic(
                            code="installation_conflict", plugin=plugin.wheel.name
                        )
                    )
            if diagnostics:
                return result.model_copy(
                    update={
                        "exit_code": 1,
                        "plugins": tuple(actions),
                        "diagnostics": tuple(diagnostics),
                    }
                )
            if dry_run:
                control.check()
                return result.model_copy(
                    update={
                        "state": "planned",
                        "exit_code": 0,
                        "plugins": tuple(
                            a.model_copy(update={"status": "planned"}) for a in actions
                        ),
                    }
                )
            if any(a.action == "install" for a in actions):
                backend.require_uv()  # Before any mutation, even creation of a store.
            # Detect unusable existing environments before installing anything.
            for index, plugin in enumerate(plugins):
                if actions[index].action == "reuse":
                    current = plugin.wheel.name
                    record = _record(plugin, inventory)
                    assert record is not None
                    verify_interpreter(
                        record, root, prepared.lock.target, prepared.directory, control
                    )
                    actions[index] = actions[index].model_copy(
                        update={"status": "reused", "interpreter_verified": True}
                    )
            applying = True
            for index, plugin in enumerate(plugins):
                current = plugin.wheel.name
                control.check()
                if actions[index].action == "install":
                    closure = prepared.directory / "closures" / plugin.wheel.name
                    record = install_extension(
                        closure / plugin.wheel.filename,
                        plugin.wheel.sha256,
                        directory=root,
                        requirements=prepared.directory
                        / "requirements"
                        / plugin.wheel.name
                        if plugin.requirements
                        else None,
                        wheelhouse=closure if plugin.requirements else None,
                        control=control,
                    )
                    if not installation_matches(plugin, record):
                        raise PluginError("installation_conflict")
                    actions[index] = actions[index].model_copy(
                        update={"status": "installed"}
                    )
                    verify_interpreter(
                        record, root, prepared.lock.target, prepared.directory, control
                    )
                    actions[index] = actions[index].model_copy(
                        update={"interpreter_verified": True}
                    )
            # Final read and stdlib-only probes cover newly installed and reused records.
            inventory, active = _state(root, control)
            for index, plugin in enumerate(plugins):
                current = plugin.wheel.name
                record = _record(plugin, inventory)
                if record is None or not installation_matches(plugin, record):
                    raise PluginError("final_inventory_mismatch")
                actions[index] = actions[index].model_copy(
                    update={"interpreter_verified": False}
                )
                verify_interpreter(
                    record, root, prepared.lock.target, prepared.directory, control
                )
                actions[index] = actions[index].model_copy(
                    update={
                        "active": record in active.activations,
                        "interpreter_verified": True,
                    }
                )
            control.check()
            return result.model_copy(
                update={"state": "complete", "exit_code": 0, "plugins": tuple(actions)}
            )
    except (KeyboardInterrupt, InstallationCancelled):
        code, exit_code = "sync_cancelled", 130
    except LockError as error:
        code, exit_code = error.code, 2
    except PluginError as error:
        code, exit_code = str(error), 2
    except (OSError, ValueError):
        code, exit_code = "sync_input_or_io_error", 2
    # Do not trust an exception's position relative to atomic publication.
    # A fresh, independently bounded read can confirm visible progress.
    uncertain = code == "installation_cleanup_failed"
    if applying and root is not None:
        try:
            inventory, active = _state(root, InstallControl(time.monotonic() + 2))
            for index, plugin in enumerate(plugins):
                record = _record(plugin, inventory)
                if record is not None and installation_matches(plugin, record):
                    actions[index] = actions[index].model_copy(
                        update={
                            "status": "reused"
                            if actions[index].action == "reuse"
                            else "installed",
                            "active": record in active.activations,
                        }
                    )
                elif actions[index].status == "installed":
                    actions[index] = actions[index].model_copy(
                        update={"status": "unconfirmed", "interpreter_verified": False}
                    )
                    uncertain = True
                elif plugin.wheel.name == current:
                    actions[index] = actions[index].model_copy(
                        update={"status": "failed"}
                    )
        except (OSError, PluginError):
            uncertain = True
            actions = [
                a.model_copy(
                    update={
                        "status": "unconfirmed",
                        "active": None,
                        "interpreter_verified": False,
                    }
                )
                if a.status == "installed" or a.name == current
                else a
                for a in actions
            ]
    elif current is not None:
        actions = [
            a.model_copy(update={"status": "failed"}) if a.name == current else a
            for a in actions
        ]
    state = (
        "unconfirmed"
        if uncertain
        else "interrupted"
        if exit_code == 130
        else "partial"
        if applying
        else "refused"
    )
    return result.model_copy(
        update={
            "state": state,
            "exit_code": exit_code,
            "plugins": tuple(actions),
            "diagnostics": (Diagnostic(code=code, plugin=current),),
        }
    )
