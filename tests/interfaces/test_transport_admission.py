"""Pre-decoder refusals on every actual REST and MCP HTTP adapter contract."""

import importlib
import json

import pytest
from fastapi.testclient import TestClient
from oci.helpers import IMAGE
from repository_interfaces.conftest import evidence
from starlette.requests import Request

from apizr.execution.policy import ExecutionPolicy
from apizr.generators.mcp.generator import generate as mcp_generate
from apizr.generators.rest.generator import generate as rest_generate
from apizr.inspection import inspect_source
from apizr.oci.model import ExecutionPolicyV2
from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.output import write_bundle

SOURCE = b"def echo(x: int): return x\n"
VARIANTS = [
    "single-direct",
    "single-local",
    "single-oci",
    "repository-direct",
    "repository-local",
    "repository-oci",
]


def adapter(root, variant, target):
    repository = variant.startswith("repository")
    policy = (
        ExecutionPolicy()
        if variant.endswith("local")
        else ExecutionPolicyV2()
        if variant.endswith("oci")
        else None
    )
    if repository:
        write_bundle(
            root,
            render_repository_bundle(
                *evidence(
                    {"admission_sample.py": SOURCE},
                    selected=("python:admission_sample:echo",),
                    modes=(policy.backend if policy else "direct",),
                    interfaces=(target,),
                ),
                interface=target,
                execution_policy=policy,
                runtime_image=IMAGE if variant.endswith("oci") else None,
            ),
        )
        package = (
            "apizr.governed_repository" if policy else "apizr.repository_interfaces"
        )
        module = importlib.import_module(
            package + (f".{target}" if policy else f".{target}_runtime")
        )
        return (module.create_app if target == "rest" else module.create_server)(root)
    (rest_generate if target == "rest" else mcp_generate)(
        inspect_source(SOURCE, module_name="admission_sample"),
        SOURCE,
        root,
        execution_policy=policy,
        runtime_image=IMAGE if variant.endswith("oci") else None,
    )
    package = (
        "apizr.governed_oci"
        if variant.endswith("oci")
        else "apizr.governed"
        if policy
        else f"apizr.generators.{target}"
    )
    module = importlib.import_module(package + (f".{target}" if policy else ".runtime"))
    factory = module.create_app if target == "rest" else module.create_server
    if policy:
        return factory(root)
    plan = json.loads((root / f"apizr-{target}.json").read_bytes())
    if target == "rest":
        plan["endpoints"] = plan["capabilities"]
    return factory(root, plan)


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("target", ["rest", "mcp"])
def test_all_transports_refuse_structure_before_decoder_and_recover(
    tmp_path, monkeypatch, variant, target
):
    import sys

    monkeypatch.delitem(sys.modules, "admission_sample", raising=False)
    monkeypatch.setattr("apizr.oci.docker.DockerProvider.probe", lambda *args: None)
    monkeypatch.setattr(
        "apizr.repository_execution.docker.RepositoryDockerProvider.probe",
        lambda *args: None,
    )
    instance = adapter(tmp_path / "bundle", variant, target)
    app = (
        instance
        if target == "rest"
        else instance.streamable_http_app(stateless_http=True, json_response=True)
    )
    route = (
        "/capabilities/"
        + ("admission_sample." if variant.startswith("repository") else "")
        + "echo"
        if target == "rest"
        else "/mcp"
    )
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        with monkeypatch.context() as patch:

            async def forbidden(*args, **kwargs):
                raise AssertionError("framework/SDK decoder reached before admission")

            patch.setattr(Request, "json" if target == "rest" else "body", forbidden)
            for raw in (
                b"{" + b'"x":' + b"[" * 65 + b"0" + b"]" * 65 + b"}",
                b"[" + b"0," * 100000 + b"0]",
            ):
                response = client.post(
                    route,
                    content=raw,
                    headers={
                        "content-type": "application/json",
                        "accept": "application/json, text/event-stream",
                    },
                )
                assert response.status_code == 422
                assert len(response.content) < 100
        if target == "rest":
            assert client.get("/health").json() == {"status": "ok"}
            if variant.endswith("direct"):
                assert client.post(route, json={"x": 7}).json() == 7
        else:
            response = client.post(
                route,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "admission-probe", "version": "1"},
                    },
                },
                headers={"accept": "application/json, text/event-stream"},
            )
            assert response.status_code == 200, response.text
            assert "serverInfo" in response.json()["result"]


@pytest.mark.parametrize("variant", VARIANTS)
def test_emitted_stdio_refuses_before_sdk_parser_then_handles_ping(
    tmp_path, monkeypatch, variant
):
    import asyncio
    import sys

    monkeypatch.delitem(sys.modules, "admission_sample", raising=False)
    monkeypatch.setattr("apizr.oci.docker.DockerProvider.probe", lambda *args: None)
    monkeypatch.setattr(
        "apizr.repository_execution.docker.RepositoryDockerProvider.probe",
        lambda *args: None,
    )
    root = tmp_path / "bundle"
    adapter(root, variant, "mcp")
    marker = tmp_path / "decoder-reached"
    # Observation is confined to this test child. Production uses the public
    # SDK stdin argument; it never patches the SDK adapter or private helpers.
    script = """import runpy, sys
from pathlib import Path
from mcp.server import stdio
marker = Path(sys.argv[2])
original = stdio.types.jsonrpc_message_adapter.validate_json
def observed(raw, *args, **kwargs):
    if "ADMISSION_PROBE" in raw:
        marker.touch()
    return original(raw, *args, **kwargs)
stdio.types.jsonrpc_message_adapter.validate_json = observed
"""
    # Only provider startup is substituted: these probes never invoke a worker.
    # Real Docker execution is qualified by the existing native transport tests.
    if variant.endswith("oci"):
        script += """import builtins
original_import = builtins.__import__
def instrument(name, globals=None, locals=None, fromlist=(), level=0):
    module = original_import(name, globals, locals, fromlist, level)
    if name in {"apizr_governed.oci.docker", "apizr_governed.repository_execution.docker"}:
        for provider in ("DockerProvider", "RepositoryDockerProvider"):
            if hasattr(module, provider):
                getattr(module, provider).probe = lambda *args: None
    return module
builtins.__import__ = instrument
"""
    script += """filename = sys.argv[1]
sys.argv = [filename]
runpy.run_path(filename, run_name="__main__")
"""

    async def exercise():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            str(root / "server.py"),
            str(marker),
            "oci" if variant.endswith("oci") else "local",
            cwd=root,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        async def send(raw):
            process.stdin.write(raw + b"\n")
            await process.stdin.drain()

        async def response(identity):
            while True:
                line = await asyncio.wait_for(process.stdout.readline(), 15)
                assert line, "standalone server exited before response"
                value = json.loads(line)
                if value.get("id") == identity:
                    return value

        try:
            await send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 0,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-11-25",
                            "capabilities": {},
                            "clientInfo": {"name": "wire-admission", "version": "1"},
                        },
                    }
                ).encode()
            )
            assert "result" in await response(0)
            await send(b'{"jsonrpc":"2.0","method":"notifications/initialized"}')
            await send(
                b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"ADMISSION_PROBE":'
                + b"[" * 65
                + b"0"
                + b"]" * 65
                + b"}}"
            )
            await send(b'{"jsonrpc":"2.0","id":2,"method":"ping"}')
            assert "result" in await response(2)
            assert not marker.exists(), "unadmitted frame reached SDK decoder"
        finally:
            process.stdin.close()
            if process.returncode is None:
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                process.kill()
                await asyncio.wait_for(process.wait(), 5)

    asyncio.run(exercise())
