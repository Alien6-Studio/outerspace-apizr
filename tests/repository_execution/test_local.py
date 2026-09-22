import sys

import pytest

from apizr.execution.policy import BackendCapabilities, ExecutionPolicy
from apizr.execution.serialization import canonical_bytes, digest
from apizr.repository_execution.model import Request
from apizr.repository_execution.supervisor import execute
from apizr.repository_execution.worker import handle

from .helpers import planned


@pytest.mark.parametrize(
    "source,payload,value",
    [
        (None, {}, 7),
        ("async def run(x: int): return x + 1", {"x": 3}, 4),
        ("def run(x: int = 2, /, *, y: int = 3): return x+y", {"y": 4}, 6),
        ("def run(): return {'actual':'not enforced'}", {}, {"actual": "not enforced"}),
    ],
)
def test_real_fresh_local_execution(source, payload, value):
    plan, exposure, sources, _ = planned(source)
    assert execute(plan, exposure, sources, payload).value == value
    assert "sample" not in sys.modules and "sample.api" not in sys.modules


def test_mutable_defaults_reset():
    plan, exposure, sources, _ = planned(
        "def run(x: list[int] = []):\n    x.append(1)\n    return x"
    )
    for _ in range(2):
        assert execute(plan, exposure, sources, {}).value == [1]


@pytest.mark.parametrize(
    "source,status",
    [
        ("def run():\n    while True: pass", "timeout"),
        ("import os\ndef run(): os._exit(17)", "worker_failed"),
        ("def run(): raise RuntimeError('SECRET /host/path')", "execution_failed"),
        ("def run(): return float('nan')", "result_invalid"),
        ("def run(): return 'x' * 4096", "output_limit"),
    ],
)
def test_timeout_crash_and_outputs(source, status):
    plan, exposure, sources, _ = planned(
        source,
        policy=ExecutionPolicy.model_validate(
            {"limits": {"wall_time_ms": 1500, "max_output_bytes": 256}}
        ),
    )
    result = execute(plan, exposure, sources, {})
    assert result.status == status and result.value is None
    assert "SECRET" not in result.model_dump_json()


def test_input_and_policy_failures(monkeypatch):
    plan, exposure, sources, _ = planned()
    assert execute(plan, exposure, sources, {"extra": 1}).status == "invalid_input"
    assert execute(plan, b"changed", sources, {}).status == "binding_failed"
    import apizr.repository_execution.supervisor as supervisor

    monkeypatch.setattr(
        supervisor, "local_capabilities", lambda: BackendCapabilities(available=False)
    )
    assert execute(plan, exposure, sources, {}).status == "policy_refused"


def stage(root, plan, exposure, sources):
    for name, content in {
        **sources,
        "repository-interface.json": canonical_bytes(plan.repository_interface),
        "exposure-plan.json": exposure,
    }.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def test_worker_request_digest_input_source_and_binding(tmp_path):
    plan, exposure, sources, _ = planned()
    stage(tmp_path, plan, exposure, sources)
    request = Request(plan=plan, plan_digest=digest(plan), arguments={})
    assert handle(request, tmp_path).value == 7
    assert not any(n.startswith("sample") for n in sys.modules)
    assert (
        handle(
            request.model_copy(update={"plan_digest": digest(plan.policy)}), tmp_path
        ).status
        == "binding_failed"
    )
    assert (
        handle(request.model_copy(update={"arguments": {"bad": True}}), tmp_path).status
        == "invalid_input"
    )
    (tmp_path / "source/sample/pricing.py").write_bytes(b"bad")
    assert handle(request, tmp_path).status == "binding_failed"


def test_copy_boundary_and_cleanup(tmp_path, monkeypatch):
    import apizr.repository_execution.supervisor as supervisor
    from apizr.execution.model import ExecutionResult

    plan, exposure, sources, _ = planned()
    roots = []

    def exchange(command, data, root, environment, wall, limit):
        roots.append(root)
        assert root != tmp_path and root.is_dir()
        assert {
            s.bundle_path: (root / s.bundle_path).read_bytes()
            for s in plan.repository_interface.sources
        } == sources
        assert "-I" in command and not environment
        return ExecutionResult(status="success", value=1)

    monkeypatch.setattr(supervisor, "exchange", exchange)
    assert execute(plan, exposure, sources, {}).value == 1
    assert not roots[0].exists()
    assert (
        execute(plan, exposure, sources, {}, runtime_files={"../escape": b"bad"}).status
        == "worker_failed"
    )


def test_missing_external_dependency_sanitized():
    source = "def run(): return helper()\ndef helper():\n    import definitely_missing_apizr_test_dependency\n    return 1"
    plan, exposure, sources, _ = planned(source)
    result = execute(plan, exposure, sources, {})
    assert result.status == "execution_failed" and result.value is None
