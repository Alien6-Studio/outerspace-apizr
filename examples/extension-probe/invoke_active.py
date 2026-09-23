"""Call the explicitly enabled demonstration from an installed core."""

import sys
from pathlib import Path

from apizr.extension_runtime import Limits
from apizr.local_plugins import run_extension

response = run_extension(
    "apizr-extension-probe",
    "describe",
    {"source_digest": "explicit-active-example"},
    directory=Path(sys.argv[1]),
    limits=Limits(wall_time_ms=3000),
)
assert isinstance(response.result, dict)
assert response.result["source_digest"] == "explicit-active-example"
print(response.model_dump_json())
