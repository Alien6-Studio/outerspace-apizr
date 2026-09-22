from repository_interfaces.conftest import evidence

from apizr.execution.policy import ExecutionPolicy
from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.output import write_bundle

SOURCE = b"""import os
state=[]
def run(a: int = 1, /, *, b: int = 2): return helper(a)+b
def helper(a):
    from .pricing import double
    return double(a)
def counter(default: list[int]=[]):
    state.append(1)
    default.append(1)
    return [len(state),len(default),count_support()]
def count_support():
    from .pricing import count
    return count()
def fail(): raise RuntimeError("SECRET /host/private")
def large(n: int): return "x"*n
def loop():
    while True: pass
def crash(): os._exit(17)
def environment(): return "APIZR_TEST_SECRET" in os.environ
"""
FILES = {
    "sample/__init__.py": b"from . import pricing\nINITIALIZED = True\n",
    "sample/api.py": SOURCE,
    "sample/pricing.py": b"state=[]\nasync def run(x: int): return x+1\ndef double(x: int): return 2*x\ndef count():\n    state.append(1)\n    return len(state)\n",
    "sample/admin.py": b'raise RuntimeError("UNRELATED MUST NOT EXECUTE")\n',
}
SELECTED = tuple(
    "python:sample.api:" + name
    for name in ("run", "counter", "fail", "large", "loop", "crash", "environment")
) + ("python:sample.pricing:run",)


def inputs(policy=None, transport="rest", *, files=None, selected=None):
    policy = policy or ExecutionPolicy()
    return evidence(
        files or FILES,
        selected=selected or SELECTED,
        modes=(policy.backend,),
        interfaces=(transport,),
    )


def bundle(
    root, transport="rest", *, policy=None, image=None, files=None, selected=None
):
    policy = policy or ExecutionPolicy()
    artifacts = render_repository_bundle(
        *inputs(policy, transport, files=files, selected=selected),
        interface=transport,
        execution_policy=policy,
        runtime_image=image,
    )
    write_bundle(root, artifacts)
    return root
