import json
import sys

import pytest
from oci.conftest import worker_image as worker_image
from oci.test_provider import HOST, IMAGE_INFO

from apizr.execution.model import ExecutionResult
from apizr.oci.docker import DockerProvider
from apizr.oci.model import ExecutionPolicyV2
from apizr.oci.provider import ContainerState, ProviderError
from apizr.repository_execution.docker import RepositoryDockerProvider
from apizr.repository_execution.supervisor import execute

from .helpers import IMAGE, planned


def test_real_oci_resolved_private_repository_import(worker_image):
    from repository_interfaces.conftest import evidence
    from repository_interfaces.test_local_imports import FILES, SELECTED

    from apizr.exposure import plan_bytes
    from apizr.repository_execution.planner import container_plan
    from apizr.repository_interfaces.planner import plan_repository_interface

    values = evidence(FILES, selected=(SELECTED,), modes=("oci-container",))
    contract = plan_repository_interface(
        *values, interface="rest", execution_mode="oci-container"
    )
    exposure = plan_bytes(values[4])
    plan = container_plan(
        contract, exposure, SELECTED, ExecutionPolicyV2(), worker_image
    )
    sources = {s.bundle_path: values[-1][s.source_path] for s in contract.sources}
    result = execute(plan, exposure, sources, {"value": 3})
    assert result.status == "success" and result.value == 6
    assert [c.capability_id for c in contract.capabilities] == [SELECTED]


def test_exact_shared_launch_controls_with_only_fixed_entrypoint_difference(
    tmp_path, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        DockerProvider,
        "run",
        lambda self, args, **kw: calls.append((list(args), kw)) or b"",
    )
    plan, _, _, _ = planned(policy=ExecutionPolicyV2())
    DockerProvider().create("name", plan, tmp_path, {"TOKEN": "private"})
    RepositoryDockerProvider().create_repository(
        "name", plan, tmp_path, {"TOKEN": "private"}
    )
    old, new = calls
    expected = [
        "apizr.repository_execution.entrypoint" if a == "apizr.oci.entrypoint" else a
        for a in old[0]
    ]
    assert new[0] == expected
    assert new[1] == {"timeout": 10, **old[1]}
    assert "private" not in new[0]
    assert RepositoryDockerProvider().run(["info"]) == b""


@pytest.mark.parametrize("label", [None, "wrong", "apizr.repository-runtime/v1"])
def test_repository_image_marker_and_preserved_old_probe(monkeypatch, label):
    image = json.loads(json.dumps(IMAGE_INFO))
    if label is not None:
        image["Config"]["Labels"]["org.apizr.repository.worker.protocol"] = label
    monkeypatch.setattr(
        DockerProvider,
        "run",
        lambda self, args, **kw: json.dumps(
            HOST if args[0] == "info" else image
        ).encode(),
    )
    if label == "apizr.repository-runtime/v1":
        RepositoryDockerProvider().probe(IMAGE)
    else:
        with pytest.raises(ProviderError, match="runtime_image_unavailable"):
            RepositoryDockerProvider().probe(IMAGE)


def test_second_image_inspection_identity_still_verified(monkeypatch):
    calls = []

    def run(self, args, **kw):
        if args[0] == "info":
            return json.dumps(HOST).encode()
        calls.append(1)
        return json.dumps(IMAGE_INFO if len(calls) == 1 else {}).encode()

    monkeypatch.setattr(DockerProvider, "run", run)
    with pytest.raises(ProviderError):
        RepositoryDockerProvider().probe(IMAGE)


class FakeProvider(RepositoryDockerProvider):
    def __init__(self, state=None, fail=None):
        self.state, self.fail, self.removed, self.created = state, fail, [], []

    def probe(self, runtime):
        if self.fail == "probe":
            raise ProviderError("runtime_image_unavailable")

    def create_repository(self, name, plan, root, environment):
        self.created.append((name, root, environment))
        assert (root / "source/sample/api.py").read_bytes()
        if self.fail == "create":
            raise ProviderError()

    def command(self, name):
        return ["unit-provider-placeholder"]

    def final_state(self, name, **kwargs):
        return self.state

    def remove(self, name):
        self.removed.append(name)
        if self.fail == "remove":
            raise ProviderError("cleanup_failed")


@pytest.mark.parametrize(
    "status,state,expected",
    [
        ("worker_failed", ContainerState(False, "exited", True, 137), "resource_limit"),
        ("worker_failed", ContainerState(False, "exited", False, 137), "worker_failed"),
        ("worker_failed", ContainerState(True, "running", True, 137), "worker_failed"),
        ("worker_failed", None, "worker_failed"),
        ("timeout", ContainerState(False, "exited", True, 137), "timeout"),
        ("success", None, "success"),
    ],
)
def test_oom_only_terminal_provider_evidence_and_unconditional_cleanup(
    monkeypatch, status, state, expected
):
    import apizr.repository_execution.supervisor as supervisor

    monkeypatch.setattr(
        supervisor, "exchange", lambda *args: ExecutionResult(status=status)
    )
    plan, exposure, sources, _ = planned(policy=ExecutionPolicyV2())
    provider = FakeProvider(state)
    result = execute(plan, exposure, sources, {}, provider=provider)
    assert result.status == expected and len(provider.removed) == 1
    assert not provider.created[0][1].exists()


@pytest.mark.parametrize(
    "failure,status",
    [
        ("probe", "runtime_image_unavailable"),
        ("create", "backend_unavailable"),
        ("remove", "cleanup_failed"),
    ],
)
def test_provider_failure_no_fallback(monkeypatch, failure, status):
    import apizr.repository_execution.supervisor as supervisor

    monkeypatch.setattr(
        supervisor, "exchange", lambda *args: ExecutionResult(status="success")
    )
    plan, exposure, sources, _ = planned(policy=ExecutionPolicyV2())
    provider = FakeProvider(fail=failure)
    assert execute(plan, exposure, sources, {}, provider=provider).status == status
    assert len(provider.removed) == (0 if failure == "probe" else 1)
    provider.identity = "wrong-provider"
    assert (
        execute(plan, exposure, sources, {}, provider=provider).status
        == "backend_unavailable"
    )


def test_repository_entrypoint_clears_image_environment(monkeypatch):
    import os

    from apizr.repository_execution import entrypoint, worker

    seen = []
    monkeypatch.setattr(os, "environ", {"KEEP": "ok", "IMAGE_SECRET": "bad"})
    monkeypatch.setattr(sys, "argv", ["entrypoint", "KEEP"])
    monkeypatch.setattr(os, "chdir", lambda path: seen.append(path))
    monkeypatch.setattr(worker, "main", lambda: seen.append(dict(os.environ)))
    entrypoint.main()
    assert seen == ["/bundle", {"KEEP": "ok"}]
