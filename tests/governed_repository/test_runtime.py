import sys

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp import Client
from oci.helpers import IMAGE

from apizr.execution.policy import BackendCapabilities
from apizr.governed_repository.mcp import create_server
from apizr.governed_repository.rest import create_app
from apizr.governed_repository.runtime import GovernedRuntime
from apizr.oci.model import ContainerResult, ExecutionPolicyV2
from apizr.oci.provider import ProviderError
from apizr.repository_execution.docker import RepositoryDockerProvider

from .helpers import bundle


def test_parent_never_imports_and_each_call_fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("APIZR_TEST_SECRET", "SECRET")
    root = bundle(tmp_path / "bundle")
    runtime = GovernedRuntime(root, "rest")
    for _ in range(2):
        assert runtime.invoke("python:sample.api:counter", {}).value == [1, 1, 1]
        assert runtime.invoke("python:sample.api:run", {}).value == 4
        assert runtime.invoke("python:sample.pricing:run", {"x": 4}).value == 5
    assert runtime.invoke("python:sample.api:environment", {}).value is False
    assert runtime.invoke("python:sample.api:helper", {}).status == "binding_failed"
    assert not any(
        name == "sample" or name.startswith("sample.") for name in sys.modules
    )


@pytest.mark.parametrize(
    "target",
    [
        "source/sample/api.py",
        "source/sample/pricing.py",
        "source/sample/__init__.py",
        "execution/policy.json",
        "execution/bundle.json",
        "execution/worker.py",
        "apizr_governed/repository_execution/worker.py",
        "repository-interface.json",
        "exposure-plan.json",
        "exposure-policy.json",
        "capability-catalog.json",
        "capability-graph.json",
        "repository-readiness.json",
        "plan",
        "manifest",
    ],
)
def test_post_startup_tampering_then_recovery(tmp_path, target):
    root = bundle(tmp_path / "bundle")
    runtime = GovernedRuntime(root, "rest")
    if target == "plan":
        target = next(iter(runtime.bundle.capabilities.values())).path
    if target == "manifest":
        target = "apizr-repository-rest.json"
    path = root / target
    content = path.read_bytes()
    path.write_bytes(content + b"bad")
    assert runtime.invoke("python:sample.api:run", {}).status == "binding_failed"
    path.write_bytes(content)
    assert runtime.invoke("python:sample.api:run", {}).value == 4


@pytest.mark.parametrize("backend", ["local-process", "oci-container"])
def test_backend_unavailable_never_falls_back(tmp_path, monkeypatch, backend):
    import apizr.governed_repository.runtime as runtime

    if backend == "local-process":
        root = bundle(tmp_path / "bundle")
        monkeypatch.setattr(
            runtime, "local_capabilities", lambda: BackendCapabilities(available=False)
        )
    else:
        root = bundle(tmp_path / "bundle", policy=ExecutionPolicyV2(), image=IMAGE)

        def fail(*args):
            raise ProviderError("runtime_image_unavailable")

        monkeypatch.setattr(RepositoryDockerProvider, "probe", fail)
    with pytest.raises(
        RuntimeError, match="Governed repository bundle or backend unavailable"
    ):
        GovernedRuntime(root, "rest")
    assert "sample.api" not in sys.modules


@pytest.mark.parametrize(
    "status,rest,mcp",
    [
        ("success", 200, None),
        ("invalid_input", 422, "Invalid tool arguments"),
        ("timeout", 504, "Tool execution timed out"),
        ("resource_limit", 503, "Tool execution resource limit exceeded"),
        ("worker_failed", 500, "Tool execution failed"),
    ],
)
def test_rest_mcp_status_mapping(tmp_path, monkeypatch, status, rest, mcp):
    result = ContainerResult(status=status, value=1 if status == "success" else None)
    monkeypatch.setattr(GovernedRuntime, "invoke", lambda *args: result)
    with TestClient(create_app(bundle(tmp_path / "rest"))) as client:
        assert client.post("/capabilities/sample.api.run", json={}).status_code == rest
        assert (
            client.post("/capabilities/sample.api.run", content=b"bad").status_code
            == 422
        )
        assert client.get("/health").status_code == 200
        assert client.get("/openapi.json").status_code == 200
    server = create_server(bundle(tmp_path / "mcp", "mcp"))

    async def check():
        async with Client(server) as client:
            assert len((await client.list_tools()).tools) == 8
            response = await client.call_tool("sample.api.run", {})
            assert response.is_error == (status != "success")
            if mcp:
                assert response.content[0].text == mcp
            assert (await client.call_tool("unknown", {})).is_error

    anyio.run(check)
