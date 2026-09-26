"""Retained artifact installation and consistent state shared by sync and update."""

from pathlib import Path

from apizr.local_plugins import activation, store
from apizr.local_plugins.control import InstallControl
from apizr.local_plugins.models import Installation, Inventory
from apizr.local_plugins.operations import install_extension
from apizr.plugin_lock.models import Plugin
from apizr.plugin_lock.operations import PreparedLock


def installation_state(
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


def install_prepared_plugin(
    plugin: Plugin, prepared: PreparedLock, root: Path, control: InstallControl
) -> Installation:
    """Install just this closure, using only retained validated input paths."""
    closure = prepared.directory / "closures" / plugin.wheel.name
    return install_extension(
        closure / plugin.wheel.filename,
        plugin.wheel.sha256,
        directory=root,
        requirements=prepared.directory / "requirements" / plugin.wheel.name
        if plugin.requirements
        else None,
        wheelhouse=closure if plugin.requirements else None,
        control=control,
    )
