import json
import sys
from contextlib import contextmanager

from apizr.generators.mcp import generate
from apizr.generators.mcp.runtime import create_server
from apizr.inspection import inspect_source


@contextmanager
def server_bundle(root, source, module="mcp_sample", select=None):
    source = source.encode() if isinstance(source, str) else source
    inspection = inspect_source(source, module_name=module)
    generate(inspection, source, root, select=select)
    plan = json.loads((root / "apizr-mcp.json").read_bytes())
    try:
        yield create_server(root, plan), plan
    finally:
        parts = module.split(".")
        for index in range(1, len(parts) + 1):
            sys.modules.pop(".".join(parts[:index]), None)
