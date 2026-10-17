"""Resolve canonical qualification sources for tests that patch module globals."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = tomllib.loads((ROOT / "architecture/scripts.toml").read_text())["files"]


def implementation(name):
    key = "scripts/" + Path(name).stem + ".py"
    entry = INVENTORY[key]
    assert entry["kind"] == "compatibility"
    return ROOT / entry["canonical"]
