"""Read one explicit bounded provider selection, never discover project settings."""

import json
from pathlib import Path

from apizr.contracts.json_budget import preflight_json
from apizr.extension_runtime.protocol import unique_object
from apizr.scientific_providers.contracts.selection import ProviderSelection
from apizr.workspace.files import read_regular


def load_selection(path: Path | None) -> ProviderSelection | None:
    if path is None:
        return None
    raw = read_regular(path, 65536)
    preflight_json(raw, max_bytes=65536, max_nodes=4096, max_depth=16)
    json.loads(raw, object_pairs_hook=unique_object)
    return ProviderSelection.model_validate_json(raw)
