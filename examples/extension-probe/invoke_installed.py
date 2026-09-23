"""Explicitly select and invoke the installed demonstration; no auto-activation."""

import sys
from pathlib import Path

from apizr.extension_runtime import Limits, invoke_extension
from apizr.local_plugins import list_extensions

inventory = list_extensions(directory=Path(sys.argv[1]))
plugin = next(
    item
    for item in inventory.installations
    if item.name == "apizr-extension-probe" and item.version == "0.0.0"
)
response = invoke_extension(
    plugin.python,
    plugin.module,
    "describe",
    {"source_digest": "explicit-installed-example"},
    limits=Limits(wall_time_ms=3000),
    environment={},
)
assert isinstance(response.result, dict)
assert response.result["source_digest"] == "explicit-installed-example"
print(response.model_dump_json())
