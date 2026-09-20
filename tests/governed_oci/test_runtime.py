import json

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp import Client

from apizr.governed_oci import mcp, rest
from apizr.governed_oci.runtime import GovernedRuntime
from apizr.oci.model import ContainerResult
from apizr.oci.provider import ProviderError

from .helpers import bundle, rehash


@pytest.fixture
def no_docker(monkeypatch):
    monkeypatch.setattr(
        "apizr.governed_oci.runtime.DockerProvider.probe", lambda *a: None
    )


@pytest.mark.parametrize(
    "status",
    [
        "success",
        "invalid_input",
        "timeout",
        "resource_limit",
        "backend_unavailable",
        "runtime_image_unavailable",
        "cleanup_failed",
        "binding_failed",
        "policy_refused",
        "worker_failed",
        "source_mismatch",
        "execution_failed",
        "result_invalid",
        "output_limit",
    ],
)
def test_public_mapping(no_docker, tmp_path, monkeypatch, status):
    monkeypatch.setattr(
        GovernedRuntime,
        "invoke",
        lambda *a: ContainerResult(
            status=status, value=3 if status == "success" else None
        ),
    )
    root = bundle(tmp_path / "rest", "rest", source=b"def f(): return 3")
    with TestClient(rest.create_app(root)) as client:
        response = client.post("/capabilities/f", json={})
        assert response.status_code == {
            "success": 200,
            "invalid_input": 422,
            "timeout": 504,
            "resource_limit": 503,
        }.get(status, 500)
        assert response.json() == (
            3
            if status == "success"
            else {
                "detail": {
                    "invalid_input": "Invalid request arguments",
                    "timeout": "Execution timed out",
                    "resource_limit": "Execution resource limit exceeded",
                }.get(status, "Internal server error")
            }
        )
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/openapi.json").status_code == 200
        assert client.post("/capabilities/f", content=b"bad").status_code == 422
    root = bundle(tmp_path / "mcp", "mcp", source=b"def f(): return 3")

    async def check():
        async with Client(mcp.create_server(root)) as client:
            assert len((await client.list_tools()).tools) == 1
            result = await client.call_tool("f", {})
            assert result.is_error == (status != "success")
            if status == "success":
                assert result.structured_content == 3
            else:
                assert result.content[0].text == {
                    "invalid_input": "Invalid tool arguments",
                    "timeout": "Tool execution timed out",
                    "resource_limit": "Tool execution resource limit exceeded",
                }.get(status, "Tool execution failed")
            assert (await client.call_tool("missing", {})).content[
                0
            ].text == "Unknown tool"

    anyio.run(check)


def test_invalid_finite_mcp_arguments(no_docker, tmp_path, monkeypatch):
    root = bundle(tmp_path / "mcp", "mcp", source=b"def f(): return 3")
    server = mcp.create_server(root)

    def invalid(*a):
        raise ValueError("private")

    monkeypatch.setattr(mcp, "finite_json", invalid)

    async def check():
        async with Client(server) as client:
            result = await client.call_tool("f", {})
            assert (
                result.is_error and result.content[0].text == "Invalid tool arguments"
            )

    anyio.run(check)


@pytest.mark.parametrize("status", ["backend_unavailable", "runtime_image_unavailable"])
def test_provider_failure_prevents_startup(tmp_path, monkeypatch, status):
    root = bundle(tmp_path / "rest", "rest", source=b"def f(): return 1")

    def fail(*a):
        raise ProviderError(status)

    monkeypatch.setattr("apizr.governed_oci.runtime.DockerProvider.probe", fail)
    with pytest.raises(RuntimeError, match="provider unavailable or invalid"):
        rest.create_app(root)


@pytest.mark.parametrize(
    "path",
    [
        "source/governed_sample.py",
        "execution/policy.json",
        "execution/plans/f.json",
        "execution/bundle.json",
        "apizr_governed/oci/docker.py",
        "apizr_governed/execution/worker.py",
        "apizr-rest.json",
    ],
)
def test_after_startup_tampering_fails_then_restore_succeeds(
    no_docker, tmp_path, monkeypatch, path
):
    root = bundle(tmp_path / "rest", "rest", source=b"def f(): return 1")
    runtime = GovernedRuntime(root, "rest")
    plans = runtime.plans
    monkeypatch.setattr(
        "apizr.governed_oci.runtime.execute",
        lambda *a, **kw: ContainerResult(status="success", value=1),
    )
    target = root / path
    original = target.read_bytes()
    target.write_bytes(original + b"changed")
    assert runtime.invoke("python:governed_sample:f", {}).status == "binding_failed"
    target.write_bytes(original)
    assert runtime.invoke("python:governed_sample:f", {}).value == 1
    assert runtime.plans is plans
    assert runtime.invoke("unknown", {}).status == "binding_failed"


@pytest.mark.parametrize(
    "fault",
    [
        "transport",
        "bridge_hash",
        "bridge_transport",
        "missing_runtime",
        "artifact_sets",
        "policy_digest",
        "contract_digest",
        "plan_digest",
        "policy_link",
        "runtime_link",
        "interface_link",
        "duplicate",
        "source_link",
        "ir_link",
        "readiness_link",
        "extra_capability",
        "backend",
        "provider",
    ],
)
def test_semantically_resealed_invalid_bundle_refused(no_docker, tmp_path, fault):
    from apizr.capabilities.model import Digest
    from apizr.execution.serialization import digest
    from apizr.interfaces.serialization import json_bytes
    from apizr.oci.model import ContainerPlan

    root = bundle(tmp_path / "rest", "rest", source=b"def f(): return 1")
    manifest_path = root / "apizr-rest.json"
    bridge_path = root / "execution/bundle.json"
    plan_path = root / "execution/plans/f.json"
    manifest = json.loads(manifest_path.read_bytes())
    bridge = json.loads(bridge_path.read_bytes())
    runtime = json.loads(plan_path.read_bytes())
    identity = "python:governed_sample:f"
    if fault == "transport":
        manifest["schema_version"] = "apizr.mcp/v1"
    elif fault == "bridge_transport":
        bridge["transport"] = "mcp"
    elif fault == "missing_runtime":
        key = "apizr_governed/oci/docker.py"
        bridge["artifacts"].pop(key)
        manifest["artifacts"].pop(key)
    elif fault == "policy_digest":
        bridge["policy_digest"]["value"] = "0" * 64
    elif fault == "contract_digest":
        bridge["contract_digest"]["value"] = "0" * 64
    elif fault == "plan_digest":
        bridge["capabilities"][identity]["digest"]["value"] = "0" * 64
    elif fault == "policy_link":
        runtime["policy"]["resources"]["pids"] = 33
        runtime["policy_digest"] = Digest.of_bytes(
            json_bytes(runtime["policy"])
        ).model_dump(mode="json")
    elif fault == "runtime_link":
        runtime["runtime"]["image"] = "sha256:" + "1" * 64
    elif fault == "interface_link":
        manifest["capabilities"][0]["description"] = "different"
        bridge["contract_digest"] = Digest.of_bytes(
            json_bytes(manifest["capabilities"])
        ).model_dump(mode="json")
    elif fault == "duplicate":
        manifest["capabilities"] *= 2
        bridge["contract_digest"] = Digest.of_bytes(
            json_bytes(manifest["capabilities"])
        ).model_dump(mode="json")
    elif fault == "source_link":
        manifest["ir_digest"]["value"] = "0" * 64
    elif fault in ["ir_link", "readiness_link"]:
        target = root / (
            "capability-ir.json" if fault == "ir_link" else "readiness.json"
        )
        target.write_bytes(target.read_bytes() + b" ")
    elif fault == "extra_capability":
        bridge["capabilities"]["other"] = bridge["capabilities"][identity]
    elif fault == "backend":
        bridge["backend_version"] = "other"
    elif fault == "provider":
        bridge["runtime"]["provider"] = "other"
    if fault in ["policy_link", "runtime_link"]:
        plan_path.write_bytes(json_bytes(runtime))
        bridge["capabilities"][identity]["digest"] = digest(
            ContainerPlan.model_validate(runtime)
        ).model_dump(mode="json")
    bridge_path.write_bytes(json_bytes(bridge))
    manifest_path.write_bytes(json_bytes(manifest))
    rehash(root)
    if fault in ["bridge_hash", "artifact_sets"]:
        manifest = json.loads(manifest_path.read_bytes())
        if fault == "bridge_hash":
            manifest["artifacts"]["execution/bundle.json"]["value"] = "0" * 64
        else:
            manifest["artifacts"].pop("openapi.json")
        manifest_path.write_bytes(json_bytes(manifest))
    with pytest.raises(RuntimeError, match="unavailable or invalid"):
        GovernedRuntime(root, "rest")


def test_notebook_plan_cache_and_mcp_cli(no_docker, tmp_path, monkeypatch):
    import sys

    from apizr.generate_cli import main

    from .helpers import IMAGE

    raw = {
        "cells": [
            {
                "cell_type": "code",
                "id": "sample",
                "metadata": {},
                "outputs": [],
                "execution_count": None,
                "source": ["def f(): return 1"],
            }
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path = tmp_path / "sample.ipynb"
    path.write_text(json.dumps(raw))
    policy = tmp_path / "policy.json"
    policy.write_text('{"schema_version":"apizr.execution/v2"}')
    root = tmp_path / "out"
    assert (
        main(
            [
                "mcp",
                str(path),
                "--output-dir",
                str(root),
                "--execution-policy",
                str(policy),
                "--runtime-image",
                IMAGE.image,
                "--runtime-platform",
                IMAGE.platform,
            ]
        )
        == 0
    )
    runtime = GovernedRuntime(root, "mcp")
    assert (
        runtime.original == path.read_bytes() and runtime.executable != runtime.original
    )
    server = mcp.create_server(root)
    calls = []
    monkeypatch.setattr(mcp, "create_server", lambda root: server)

    async def stdio(server):
        calls.append("stdio")

    monkeypatch.setattr(mcp, "serve_stdio", stdio)
    monkeypatch.setattr(mcp.uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    for mode in ["stdio", "streamable-http"]:
        monkeypatch.setattr(sys, "argv", ["server.py", "--transport", mode])
        mcp.main(root)
    assert calls == ["stdio", {"host": "127.0.0.1", "port": 8000}]


def test_stdio_uses_sdk_context_lifecycle(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    calls = []

    @asynccontextmanager
    async def streams():
        calls.append("enter")
        yield ("reader", "writer")
        calls.append("exit")

    async def run(*args):
        calls.append(args)

    monkeypatch.setattr(mcp, "stdio_server", streams)
    anyio.run(
        mcp.serve_stdio,
        SimpleNamespace(run=run, create_initialization_options=lambda: "options"),
    )
    assert calls == ["enter", ("reader", "writer", "options"), "exit"]
