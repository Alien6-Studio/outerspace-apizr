"""One locked target, followed by an optional conditional activation transition."""

import time
from pathlib import Path
from threading import Event

from pydantic import TypeAdapter

from apizr.extension_runtime import ExtensionError
from apizr.local_plugins import activation, backend, store
from apizr.local_plugins.control import (
    InstallationCancelled,
    InstallationTimeout,
    InstallControl,
)
from apizr.local_plugins.models import (
    PluginError,
    Version,
    canonical_name,
)
from apizr.plugin_lock.models import Diagnostic, LockError
from apizr.plugin_lock.operations import installation_matches, prepared_lock
from apizr.plugin_sync import SyncLimits
from apizr.plugin_sync.preparation import install_prepared_plugin, installation_state
from apizr.plugin_sync.probe import verify_interpreter

from .models import UpdateResult


class PreconditionRefused(PluginError):
    """A known divergence before any installation or activation is attempted."""


def update_plugin(
    name: str,
    from_version: str,
    project: Path,
    lock_path: Path,
    wheelhouse: Path,
    *,
    activate: bool = False,
    dry_run: bool = False,
    directory: Path | None = None,
    timeout_ms: int = 120000,
    cancel: Event | None = None,
) -> UpdateResult:
    """Preserve installed environments; return observed progress on handled failure."""
    result = UpdateResult(
        mode="dry-run" if dry_run else "apply",
        activation_requested=activate,
        activation="not_attempted" if activate else "not_requested",
    )
    root: Path | None = None
    attempted = False
    reused = False
    try:
        name = canonical_name(name)
        version = TypeAdapter(Version).validate_python(from_version, strict=True)
        result = result.model_copy(update={"plugin": name, "from_version": version})
        limits = SyncLimits(timeout_ms=timeout_ms)
        control = InstallControl(time.monotonic() + limits.timeout_ms / 1000, cancel)
        with prepared_lock(project, lock_path, wheelhouse, control.check) as prepared:
            result = result.model_copy(
                update={
                    "lock_sha256": prepared.result.lock_sha256,
                    "python_target": prepared.lock.target,
                }
            )
            if not prepared.result.valid:
                return result.model_copy(
                    update={"exit_code": 1, "diagnostics": prepared.result.diagnostics}
                )
            plugin = next(
                (p for p in prepared.lock.plugins if p.wheel.name == name), None
            )
            if plugin is None:
                raise PreconditionRefused("update_plugin_not_declared")
            result = result.model_copy(update={"target": plugin})
            root = store.storage_directory(directory)
            inventory, active = installation_state(root, control)
            source = next(
                (
                    r
                    for r in inventory.installations
                    if (r.name, r.version) == (name, version)
                ),
                None,
            )
            before = next((r for r in active.activations if r.name == name), None)
            result = result.model_copy(
                update={
                    "source": source,
                    "active_before": before,
                    "active_after": before,
                    "before_known": True,
                    "after_known": True,
                }
            )
            if source is None:
                raise PreconditionRefused("update_source_missing")
            target = next(
                (
                    r
                    for r in inventory.installations
                    if (r.name, r.version) == (name, plugin.wheel.version)
                ),
                None,
            )
            if target is not None and not installation_matches(plugin, target):
                raise PreconditionRefused("installation_conflict")
            result = result.model_copy(update={"target_installation": target})
            reused = target is not None
            if activate and (before is None or before not in (source, target)):
                raise PreconditionRefused("update_activation_precondition")
            result = result.model_copy(
                update={
                    "installation": "reused" if reused else "planned",
                    "activation": "unchanged"
                    if activate and before == target
                    else "planned"
                    if activate
                    else "not_requested",
                }
            )
            if dry_run:
                control.check()
                return result.model_copy(update={"state": "planned", "exit_code": 0})
            if target is None:
                backend.require_uv()  # No store mutation when backend is unavailable.
                attempted = True
                target = install_prepared_plugin(plugin, prepared, root, control)
                result = result.model_copy(
                    update={"target_installation": target, "installation": "installed"}
                )
            if not installation_matches(plugin, target):
                raise PluginError("update_target_changed")
            verify_interpreter(
                target, root, prepared.lock.target, prepared.directory, control
            )
            result = result.model_copy(update={"interpreter_verified": True})
            if activate:
                assert before is not None
                attempted = True
                changed = activation.compare_and_activate(
                    source, target, before, root=root, control=control
                )
                result = result.model_copy(
                    update={"activation": "changed" if changed else "unchanged"}
                )
            # Observe final state separately from the transition's linearization point.
            inventory, active = installation_state(root, control)
            after = next((r for r in active.activations if r.name == name), None)
            result = result.model_copy(
                update={"active_after": after, "after_known": True}
            )
            if source not in inventory.installations:
                raise PluginError("update_source_changed")
            if target not in inventory.installations:
                raise PluginError("update_target_changed")
            if activate and after != target:
                raise PluginError("update_activation_changed")
            control.check()
            return result.model_copy(update={"state": "complete", "exit_code": 0})
    except (KeyboardInterrupt, InstallationCancelled):
        code, exit_code = "update_cancelled", 130
    except InstallationTimeout:
        code, exit_code = "update_timeout", 2
    except PreconditionRefused as error:
        code, exit_code = str(error), 1
    except LockError as error:
        code, exit_code = error.code, 2
    except (PluginError, ExtensionError) as error:
        code, exit_code = str(error), 2
    except (OSError, ValueError):
        code, exit_code = "update_input_or_io_error", 2
    uncertain = code == "installation_cleanup_failed"
    if not dry_run and result.before_known and root is not None:
        try:
            inventory, active = installation_state(
                root, InstallControl(time.monotonic() + 2)
            )
            after = next((r for r in active.activations if r.name == name), None)
            plugin = result.target
            target = next(
                (
                    r
                    for r in inventory.installations
                    if plugin is not None and installation_matches(plugin, r)
                ),
                None,
            )
            if target != result.target_installation:
                result = result.model_copy(update={"interpreter_verified": False})
            result = result.model_copy(
                update={
                    "active_after": after,
                    "after_known": True,
                    "target_installation": target,
                    "installation": "reused"
                    if target and reused
                    else "installed"
                    if target
                    else "failed"
                    if attempted
                    else "not_attempted",
                    "activation": (
                        "observed_target" if target and after == target else "refused"
                    )
                    if activate
                    else "not_requested",
                }
            )
            if target is None:
                result = result.model_copy(update={"interpreter_verified": False})
        except (OSError, PluginError):
            uncertain = True
            result = result.model_copy(
                update={
                    "active_after": None,
                    "after_known": False,
                    "installation": "unconfirmed",
                    "interpreter_verified": False,
                    "activation": "unconfirmed" if activate else "not_requested",
                }
            )
    if uncertain and exit_code != 130:
        exit_code = 2
    state = (
        "unconfirmed"
        if uncertain
        else "interrupted"
        if exit_code == 130
        else "partial"
        if attempted
        else "refused"
    )
    return result.model_copy(
        update={
            "state": state,
            "exit_code": exit_code,
            "diagnostics": (Diagnostic(code=code, plugin=result.plugin),),
        }
    )
