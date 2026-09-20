import sys
from contextlib import contextmanager

from apizr.execution import ExecutionPolicy, plan
from apizr.execution.model import Request
from apizr.execution.serialization import digest
from apizr.inspection import inspect_source


def planned(source, **changes):
    source = source.encode() if isinstance(source, str) else source
    policy = ExecutionPolicy.model_validate(changes)
    return plan(
        inspect_source(source, module_name="execution_sample"), source, "f", policy
    ), source


@contextmanager
def request_root(root, source, payload=None, **changes):
    runtime, raw = planned(source, **changes)
    (root / "original").write_bytes(raw)
    target = root / runtime.executable_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    try:
        yield Request(
            plan=runtime,
            plan_digest=digest(runtime),
            arguments={} if payload is None else payload,
        )
    finally:
        sys.modules.pop("execution_sample", None)
