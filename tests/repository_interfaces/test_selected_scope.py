"""Real transports keep the full audit while importing only required sources."""

import json
import sys

import anyio
import httpx
import pytest
from exposure.test_scope import API, CHAIN, ROOT, UNRELATED
from governed.helpers import SERVER, http_server
from mcp import Client, StdioServerParameters

from apizr.execution.policy import ExecutionPolicy
from apizr.repository_execution.planner import worker_plan
from apizr.repository_execution.supervisor import execute
from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_interfaces.planner import plan_repository_interface

from .conftest import evidence


@pytest.mark.parametrize("transitive", [False, True])
@pytest.mark.parametrize("mode", ["direct", "local-process"])
def test_real_rest_and_official_stdio_preserve_unrelated_audit(
    tmp_path, transitive, mode
):
    sources = {
        **(CHAIN if transitive else {"api.py": API}),
        **UNRELATED,
        "unrelated_guard.py": b"raise RuntimeError('UNRELATED MUST NOT IMPORT')\n",
    }
    values = evidence(sources, selected=(ROOT,), modes=(mode,))
    catalog, graph, readiness = values[:3]
    audit = [item.model_dump_json() for item in values[:3]]
    assert not graph.complete
    assert any(d.path == "unused.py" for d in graph.diagnostics)
    assert not readiness.graph_complete
    assert catalog.sources
    for interface in ("rest", "mcp"):
        artifacts = render_repository_bundle(
            *values,
            interface=interface,
            execution_policy=ExecutionPolicy() if mode == "local-process" else None,
        )
        assert artifacts["source/internal.py"] == UNRELATED["internal.py"]
        assert artifacts["source/unrelated_guard.py"] == sources["unrelated_guard.py"]
        write_bundle(tmp_path / interface, artifacts)
    assert audit == [item.model_dump_json() for item in values[:3]]

    # Direct calls legitimately execute selected source in the transport.
    # Fresh-process calls retain the existing transport non-execution hook.
    server = SERVER.replace(
        "root=Path(sys.argv[1]).resolve()",
        "root=Path(sys.argv[1]).resolve()\nsys.path.insert(0,str(root))",
    )
    if mode == "direct":
        server = server.replace(
            '"/source/" in str(args[0].co_filename)',
            'Path(args[0].co_filename).name in {"internal.py", "unused.py", "unrelated_guard.py"}',
        )
    with (
        http_server(tmp_path / "rest", "rest", server=server) as (url, process),
        httpx.Client(base_url=url, timeout=10) as client,
    ):
        result = client.post("/capabilities/api.add", json={"left": 2, "right": 3})
        assert result.status_code == 200 and result.json() == 5
        assert set(client.get("/openapi.json").json()["paths"]) == {
            "/health",
            "/capabilities/api.add",
        }
        for name in (
            "internal.events",
            "unused.other",
            "helper.normalize",
            "mathutil.adjust",
        ):
            assert client.post("/capabilities/" + name, json={}).status_code == 404
        assert process.poll() is None

    async def check():
        async with Client(
            StdioServerParameters(
                command=sys.executable,
                args=[str(tmp_path / "mcp/server.py")],
                cwd=tmp_path / "mcp",
            ),
            read_timeout_seconds=10,
        ) as client:
            assert [tool.name for tool in (await client.list_tools()).tools] == [
                "api.add"
            ]
            result = await client.call_tool("api.add", {"left": 2, "right": 3})
            assert not result.is_error
            assert result.structured_content == {"result": 5}
            assert json.loads(result.content[0].text) == result.structured_content

    anyio.run(check)


def test_fresh_local_worker_does_not_import_unrelated_initialization():
    from apizr.exposure import plan_bytes

    values = evidence(
        {"api.py": API, **UNRELATED, "broken.py": b"raise RuntimeError('UNRELATED')\n"},
        selected=(ROOT,),
        modes=("local-process",),
    )
    contract = plan_repository_interface(
        *values, interface="rest", execution_mode="local-process"
    )
    exposure = plan_bytes(values[4])
    plan = worker_plan(contract, exposure, ROOT, ExecutionPolicy())
    sources = {
        source.bundle_path: values[-1][source.source_path]
        for source in contract.sources
    }
    result = execute(plan, exposure, sources, {"left": 2, "right": 3})
    assert result.status == "success" and result.value == 5
    assert [cap.capability_id for cap in contract.capabilities] == [ROOT]
