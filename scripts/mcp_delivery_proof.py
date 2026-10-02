"""Reuse installed locked MCP wheels and the existing registry/TSA batch fixture."""

import hashlib
import json
from pathlib import Path

from smoke_extension_packaging import snapshot
from smoke_mcp_server import prepare_wheels
from smoke_oci_plugin import lock_wheels


def install(python, store, work, command):
    root = work / "mcp-delivery-install"
    root.mkdir()
    house = root / "wheels"
    prepare_wheels(root, str(python), house)
    lock = root / "mcp.lock"
    lock_wheels(house, lock)
    wheel = next(house.glob("outerspace_apizr_mcp-*.whl"))
    before = snapshot(python.parent.parent)
    base = [python, "-I", "-B", "-m", "apizr.cli", "plugins"]
    command(
        *base,
        "install",
        wheel,
        "--sha256",
        hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "--requirements",
        lock,
        "--wheelhouse",
        house,
        "--plugins-dir",
        store,
    )
    command(
        *base,
        "enable",
        "outerspace-apizr-mcp",
        "--version",
        "0.4.3",
        "--plugins-dir",
        store,
    )
    records = json.loads(command(*base, "list", "--json", "--plugins-dir", store))[
        "installations"
    ]
    installed = next(r for r in records if r["name"] == "outerspace-apizr-mcp")
    command(
        python,
        "-I",
        "-B",
        "-c",
        "import importlib.util as u; assert all(u.find_spec(n) is None for n in ('mcp','apizr_mcp','apizr_oci','apizr_attest'))",
    )
    command(
        installed["python"],
        "-I",
        "-B",
        "-c",
        "import importlib.util as u; from importlib.metadata import version; assert version('outerspace-apizr-mcp')=='0.4.3'; assert all(u.find_spec(n) is None for n in ('apizr_oci','apizr_attest'))",
    )
    assert snapshot(python.parent.parent) == before
    (work / "mcp-delivery-install.json").write_text(
        json.dumps(
            {"version": "0.4.3", "core_unchanged": True, "isolated_plugins": True}
        )
    )
    return Path(installed["python"])
