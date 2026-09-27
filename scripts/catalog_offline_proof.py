"""Installed catalog inspection/export and separate closures under OS network denial."""

import json
import socket
import subprocess
import sys
from pathlib import Path

from apizr.local_plugins import list_extensions
from apizr.plugin_catalog import load_catalog, resolve_profile
from apizr.plugin_lock import check_lock
from apizr.plugin_sync import sync_plugins
from apizr.plugins_cli import main


def snapshot(root):
    import hashlib

    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def main_script():
    root = Path(sys.argv[1])
    core = root / "core"
    before = snapshot(core)
    active = (root / "plugins/activations.json").read_bytes()
    house = root / "wheels"
    path = root / "catalog/catalogue.json"
    catalog = load_catalog(path)
    store = root / "catalog-offline-store"
    plans = {}

    def forbidden(*args, **kwargs):
        raise AssertionError("catalog executed a process or accessed the network")

    popen, network = subprocess.Popen, socket.socket
    try:
        subprocess.Popen = forbidden
        socket.socket = forbidden
        assert main(["catalog", "list", "--catalog", str(path), "--json"]) == 0
        for entry in catalog.entries:
            assert (
                main(
                    [
                        "catalog",
                        "show",
                        entry.wheel.name,
                        "--version",
                        entry.wheel.version,
                        "--catalog",
                        str(path),
                        "--json",
                    ]
                )
                == 0
            )
        for profile in catalog.profiles:
            plan = root / ("offline-" + profile.name)
            resolve_profile(catalog, profile.name, house, plan)
            assert check_lock(
                plan / "apizr.toml", plan / "apizr.plugins.lock.json", house
            ).valid
            plans[profile.name] = plan
    finally:
        subprocess.Popen, socket.socket = popen, network
    assert not store.exists() and snapshot(core) == before
    for plan in plans.values():
        result = sync_plugins(
            plan / "apizr.toml",
            plan / "apizr.plugins.lock.json",
            house,
            directory=store,
        )
        assert result.exit_code == 0, result
    records = list_extensions(directory=store).installations
    assert len(records) == 3 and len({r.environment_id for r in records}) == 3
    assert not list_extensions(directory=store, active=True).installations
    closures = {r.name: [d.name for d in r.dependencies] for r in records}
    assert "apizr-oci" in closures["apizr-attest"]
    assert "mcp" in closures["apizr-mcp"] and "mcp" not in closures["apizr-oci"]
    assert (
        snapshot(core) == before
        and (root / "plugins/activations.json").read_bytes() == active
    )
    # This file is evidence only. Installation does not qualify business operations;
    # the existing real MCP and Docker/Attest proofs exercise those separately.
    (root / "catalog-offline.json").write_text(
        json.dumps(
            {
                "success": True,
                "closures": closures,
                "core_unchanged": True,
                "activations_unchanged": True,
                "network_denied": True,
            }
        )
    )


if __name__ == "__main__":
    main_script()
