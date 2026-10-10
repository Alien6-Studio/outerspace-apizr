"""Completed real Runs served by the emitted HTTP and official MCP transports."""

import json
import shutil
import sys

import anyio
import httpx
import pytest
from governed.helpers import SERVER, http_server
from mcp import Client, StdioServerParameters

from apizr.experiments.outputs import parse_output_declaration
from apizr.experiments.planning import RunOptions
from apizr.experiments.runner import run_experiment
from apizr.generators.notebooks import inspect_notebook_bytes
from apizr.repository_interfaces.output import write_bundle

from .exposure_support import project
from .test_exposure import compile_case


@pytest.mark.parametrize("notebook", [False, True])
def test_real_run_rest_mcp_parity_after_project_and_store_removal(tmp_path, notebook):
    path = project(tmp_path / "research", notebook=notebook, resources=False)
    source = path.read_bytes()
    executable = (
        inspect_notebook_bytes(source, module_name="serving").python_source.encode()
        if notebook
        else source
    )
    assert not (path.parent / "model.json").exists()
    assert not (path.parent / "debug.json").exists()
    record = run_experiment(
        path,
        options=RunOptions(
            outputs=tuple(
                parse_output_declaration(value)
                for value in ("model=model.json", "debug=debug.json")
            )
        ),
    )
    assert record.run.status == "success"
    assert path.read_bytes() == source
    assert (path.parent / "model.json").read_bytes() == b'{"multiplier": 3}'
    assert (path.parent / "debug.json").read_bytes() == b'{"private": true}'
    selected = {}
    for interface in ("rest", "mcp"):
        result = compile_case((path, record), interface=interface)
        assert result.bundle["source/serving.py"] == executable
        write_bundle(tmp_path / interface, result.bundle)
        selected[interface] = result.result.binding
    assert selected["rest"].outputs == selected["mcp"].outputs
    assert selected["rest"].run_digest == selected["mcp"].run_digest
    assert selected["rest"].repository_digest == selected["mcp"].repository_digest
    shutil.rmtree(path.parent)
    server = SERVER.replace(
        "root=Path(sys.argv[1]).resolve()",
        "root=Path(sys.argv[1]).resolve()\nsys.path.insert(0,str(root))",
    ).replace(
        '"/source/" in str(args[0].co_filename)',
        'Path(args[0].co_filename).name in {"admin.py", "unrelated.py"}',
    )
    expected = {"predictions": [[12, True]]}
    with (
        http_server(tmp_path / "rest", "rest", server=server) as (url, process),
        httpx.Client(base_url=url, timeout=10) as client,
    ):
        response = client.post(
            "/capabilities/serving.predict", json={"request": {"value": 4}}
        )
        assert response.status_code == 200 and response.json() == expected
        paths = client.get("/openapi.json").json()["paths"]
        assert [name for name, methods in paths.items() if "post" in methods] == [
            "/capabilities/serving.predict"
        ]
        assert client.post("/capabilities/serving.train", json={}).status_code == 404
        assert (
            client.post(
                "/capabilities/serving.predict", json={"request": {"value": "bad"}}
            ).status_code
            == 422
        )
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
                "serving.predict"
            ]
            result = await client.call_tool(
                "serving.predict", {"request": {"value": 4}}
            )
            assert not result.is_error
            assert result.structured_content == expected
            assert json.loads(result.content[0].text) == result.structured_content
            assert (
                await client.call_tool("serving.predict", {"request": {"value": "bad"}})
            ).is_error

    anyio.run(check)
    # The guard is retained verbatim; importing the bundle must not retrain.
    assert not (tmp_path / "mcp/debug.json").exists()
    assert not (tmp_path / "rest/debug.json").exists()
