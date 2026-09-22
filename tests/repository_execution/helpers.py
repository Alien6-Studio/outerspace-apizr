from oci.helpers import IMAGE
from repository_interfaces.conftest import evidence

from apizr.execution.policy import ExecutionPolicy
from apizr.exposure import plan_bytes
from apizr.oci.model import ExecutionPolicyV2
from apizr.repository_execution.planner import container_plan, worker_plan
from apizr.repository_interfaces.planner import plan_repository_interface


def planned(source=None, *, policy=None, image=None, interface="rest", files=None):
    policy = policy or ExecutionPolicy()
    if source is not None:
        files = {
            "sample/api.py": source.encode() if isinstance(source, str) else source
        }
    if files is None:
        files = {
            "sample/__init__.py": b'"""real package"""\n',
            "sample/api.py": b"def run(x: int = 2, /, *, y: int = 3): return helper(x) + y\ndef helper(x):\n    from .pricing import calculate\n    return calculate(x)\n",
            "sample/pricing.py": b"def calculate(x: int): return x * 2\n",
            "sample/admin.py": b"raise RuntimeError('UNRELATED')\n",
        }
    inputs = evidence(
        files,
        selected=("python:sample.api:run",),
        modes=(policy.backend,),
        interfaces=(interface,),
    )
    contract = plan_repository_interface(
        *inputs, interface=interface, execution_mode=policy.backend
    )
    exposure = plan_bytes(inputs[4])
    if isinstance(policy, ExecutionPolicyV2):
        plan = container_plan(
            contract, exposure, "python:sample.api:run", policy, image or IMAGE
        )
    else:
        plan = worker_plan(contract, exposure, "python:sample.api:run", policy)
    sources = {s.bundle_path: inputs[-1][s.source_path] for s in contract.sources}
    return plan, exposure, sources, inputs
