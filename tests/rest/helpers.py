import json
import sys
from contextlib import contextmanager
from types import SimpleNamespace

from apizr.generators.rest import generate, runtime
from apizr.inspection import inspect_source


@contextmanager
def application(root, source, *, module_name="rest_sample", select=None):
    source = source.encode() if isinstance(source, str) else source
    inspected = inspect_source(source, module_name=module_name)
    generate(inspected, source, root, select=select)
    parts = module_name.split(".")
    names = [".".join(parts[:i]) for i in range(1, len(parts) + 1)]
    before = {name: sys.modules[name] for name in names if name in sys.modules}
    try:
        manifest = json.loads((root / "apizr-rest.json").read_bytes())
        plan = {**manifest, "endpoints": manifest["capabilities"]}
        # Exercise the exact standalone adapter source copied to generated app.py.
        # Separate subprocess/integrity tests also import the emitted app itself.
        app = runtime.create_app(root, plan)
        yield SimpleNamespace(**vars(runtime), app=app, PLAN=plan)
    finally:
        for name in names:
            sys.modules.pop(name, None)
        sys.modules.update(before)
