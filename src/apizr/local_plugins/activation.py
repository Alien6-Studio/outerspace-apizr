"""Explicit activation snapshots and admission to the existing invocation runtime."""

import json
import os
import stat
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from threading import Event
from typing import Literal

from pydantic import ConfigDict, Field, JsonValue

from apizr.capabilities.types import ValueModel
from apizr.execution.protocol import finite_json
from apizr.extension_runtime import (
    CleanupFailed,
    InvalidInvocation,
    Limits,
    PrerequisiteMissing,
    Response,
    SizeLimitExceeded,
    invoke_extension,
)
from apizr.extension_runtime.protocol import unique_object

from . import retirement, store, usage
from .control import InstallControl
from .models import Installation, Inventory, PluginError, canonical_name

DEFAULT_LIMITS = Limits()


class Activations(ValueModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    schema_version: Literal["apizr.active-extensions/v1"] = Field(
        default="apizr.active-extensions/v1", alias="schema"
    )
    activations: list[Installation] = Field(
        default_factory=list[Installation], max_length=1000
    )


def _name(value: str) -> str:
    try:
        return canonical_name(value)
    except ValueError:
        raise PluginError("invalid_plugin_name") from None


def _read(root: Path) -> Activations:
    try:
        descriptor = os.open(
            root / "activations.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        )
    except FileNotFoundError:
        return Activations()
    try:
        with os.fdopen(descriptor, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError()
            raw = source.read(store.MAX_INVENTORY_BYTES + 1)
        if len(raw) > store.MAX_INVENTORY_BYTES:
            raise ValueError()
        state = Activations.model_validate(
            json.loads(raw, object_pairs_hook=unique_object), strict=True
        )
        if len({item.name for item in state.activations}) != len(state.activations):
            raise ValueError()
        return state
    except (ValueError, RecursionError):
        raise PluginError("invalid_activation") from None


def _publish(root: Path, records: list[Installation]) -> None:
    if len(records) > 1000:
        raise PluginError("activation_full")
    state = Activations(activations=sorted(records, key=lambda item: item.name))
    raw = state.model_dump_json(by_alias=True).encode() + b"\n"
    if len(raw) > store.MAX_INVENTORY_BYTES:
        raise PluginError("activation_full")
    store.atomic_write(root / "activations.json", raw)


def _validate_binding(record: Installation, inventory: Inventory) -> None:
    if record not in inventory.installations:
        raise PluginError("activation_mismatch")


def validated_activations(root: Path, inventory: Inventory) -> Activations:
    """Read bindings and reject any record detached from its installation."""
    state = _read(root)
    for record in state.activations:
        _validate_binding(record, inventory)
    return state


def _interpreter(record: Installation, root: Path) -> None:
    python = Path(record.python)
    environment = root / "environments" / record.environment_id
    # The interpreter itself is normally a symlink to the prepared Python.
    # Its containing environment must not have been redirected elsewhere.
    try:
        resolved_parent = python.parent.resolve(strict=True)
    except FileNotFoundError:
        raise PrerequisiteMissing() from None
    except (OSError, RuntimeError):  # Symlink loops differ between Python versions.
        raise PluginError("invalid_inventory") from None
    if resolved_parent != environment / "venv/bin":
        raise PluginError("invalid_inventory")
    if not python.is_file() or not os.access(python, os.X_OK):
        raise PrerequisiteMissing()


def enable_extension(
    name: str, version: str, *, directory: Path | None = None
) -> Installation:
    name = _name(name)
    try:
        root = store.storage_directory(directory)
        if not root.exists():
            raise PluginError("plugin_not_installed")
        with store.installation_lock(root, create=False):
            retirement.refuse_pending(root, name, version)
            inventory = store.read_inventory(root)
            selected = next(
                (
                    item
                    for item in inventory.installations
                    if (item.name, item.version) == (name, version)
                ),
                None,
            )
            if selected is None:
                raise PluginError("plugin_not_installed")
            _interpreter(selected, root)
            state = _read(root)
            if selected in state.activations:
                return selected
            _publish(
                root,
                [item for item in state.activations if item.name != name] + [selected],
            )
            return selected
    except OSError:
        raise PluginError("activation_unavailable") from None


def disable_extension(name: str, *, directory: Path | None = None) -> None:
    name = _name(name)
    try:
        root = store.storage_directory(directory)
        if not root.exists():
            return
        with store.installation_lock(root, create=False):
            state = _read(root)
            remaining = [item for item in state.activations if item.name != name]
            if remaining != state.activations:
                _publish(root, remaining)
    except OSError:
        raise PluginError("activation_unavailable") from None


def active_inventory(root: Path) -> Inventory:
    if not root.exists():
        return Inventory()
    with store.installation_lock(root, create=False):
        inventory, state = store.read_inventory(root), _read(root)
        for record in state.activations:
            _validate_binding(record, inventory)
        # Listing still reads metadata only, without probing interpreters.
        return Inventory(
            installations=[
                item for item in inventory.installations if item in state.activations
            ]
        )


def resolve_active_extension(
    name: str, *, directory: Path | None = None
) -> Installation:
    """Admit one active installation under the existing inventory lock.

    The returned binding is a snapshot: a subsequent disable blocks later
    admissions, not an already admitted invocation or server session.
    """
    name = _name(name)
    try:
        root = store.storage_directory(directory)
        if not root.exists():
            raise PluginError("plugin_not_installed")
        with store.installation_lock(root, create=False):
            inventory, state = store.read_inventory(root), _read(root)
            if not any(item.name == name for item in inventory.installations):
                raise PluginError("plugin_not_installed")
            record = next(
                (item for item in state.activations if item.name == name), None
            )
            if record is None:
                raise PluginError("plugin_inactive")
            _validate_binding(record, inventory)
            _interpreter(record, root)
        return record
    except OSError:
        raise PluginError("activation_unavailable") from None


def run_extension(
    name: str,
    operation: str,
    arguments: dict[str, JsonValue],
    *,
    directory: Path | None = None,
    limits: Limits = DEFAULT_LIMITS,
    cancel: Event | None = None,
) -> Response:
    try:
        with admitted_extension(name, directory=directory) as (record, usage_fd):
            return invoke_extension(
                record.python,
                record.module,
                operation,
                arguments,
                limits=limits,
                environment={},
                cancel=cancel,
                usage_fd=usage_fd,
            )
    except OSError:
        raise PluginError("activation_unavailable") from None


@contextmanager
def admitted_extension(
    name: str, *, directory: Path | None = None, inherit: bool = False
) -> Generator[tuple[Installation, int]]:
    """Resolve and protect atomically; exec launchers may inherit the lease FD."""
    name = _name(name)
    root = store.storage_directory(directory)
    if not root.exists():
        raise PluginError("plugin_not_installed")
    with ExitStack() as stack:
        with store.installation_lock(root, create=False):
            inventory, state = store.read_inventory(root), _read(root)
            if not any(item.name == name for item in inventory.installations):
                raise PluginError("plugin_not_installed")
            record = next((r for r in state.activations if r.name == name), None)
            if record is None:
                raise PluginError("plugin_inactive")
            _validate_binding(record, inventory)
            _interpreter(record, root)
            fd = stack.enter_context(usage.lock(root, record))
        try:
            assert fd is not None
            if inherit:
                os.set_inheritable(fd, True)
            yield record, fd
        except CleanupFailed:
            store.atomic_write(
                root / ".usage" / (record.environment_id + ".unconfirmed"),
                b"cleanup_unconfirmed\n",
            )
            raise


def read_arguments(
    path: Path, *, limits: Limits = DEFAULT_LIMITS
) -> dict[str, JsonValue]:
    try:
        limits = Limits.model_validate(limits.model_dump(), strict=True)
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise InvalidInvocation()
            raw = source.read(limits.max_request_bytes + 1)
        if len(raw) > limits.max_request_bytes:
            raise SizeLimitExceeded("request")
        value = finite_json(
            json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        )
        if not isinstance(value, dict):
            raise InvalidInvocation()
        return value
    except (ValueError, RecursionError):
        raise InvalidInvocation() from None
    except OSError:
        raise PluginError("arguments_unavailable") from None


def compare_and_activate(
    source: Installation,
    target: Installation,
    expected: Installation,
    *,
    root: Path,
    control: InstallControl,
) -> bool:
    """Select a verified target only while its full expected binding still holds.

    Returns whether this call wrote the activation. Identical concurrent
    transitions may converge; unrelated operator selections are never replaced.
    The caller has already probed the target outside the store lock.
    """
    if source.name != target.name or expected not in (source, target):
        raise PluginError("invalid_activation_transition")
    with store.installation_lock(root, create=False, control=control):
        inventory, state = store.read_inventory(root), _read(root)
        for item in state.activations:
            _validate_binding(item, inventory)
        if source not in inventory.installations:
            raise PluginError("update_source_changed")
        if target not in inventory.installations:
            raise PluginError("update_target_changed")
        current = next((r for r in state.activations if r.name == source.name), None)
        _interpreter(target, root)
        if current == target:
            return False
        if current != expected:
            raise PluginError("update_activation_changed")
        control.check()
        _publish(
            root, [r for r in state.activations if r.name != source.name] + [target]
        )
        return True
