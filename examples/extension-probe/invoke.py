"""Run with the installed core Python and an absolute extension Python argument."""

import sys
from pathlib import Path

from apizr.capabilities import document_digest, inspect_source
from apizr.extension_runtime import Limits, invoke_extension

ir = inspect_source(b"def echo(value: str) -> str: return value\n", module_name="demo")
digest = document_digest(ir).value
response = invoke_extension(
    Path(sys.argv[1]),
    "apizr_extension_probe.runtime",
    "describe",
    {"source_digest": digest},
    limits=Limits(wall_time_ms=3000, max_stdout_bytes=4096, max_stderr_bytes=1024),
    environment={},
)
assert isinstance(response.result, dict) and response.result["source_digest"] == digest
print(response.model_dump_json())
