import json
import socket
import subprocess
import sys
import time

import anyio
import httpx2
import pytest
from mcp import Client, StdioServerParameters

from apizr.generators.mcp import generate
from apizr.inspection import inspect_source

SOURCE = b'''def total(values: list[int], /, *, tax: int = 0):
    """Sum values and tax."""
    return {"total": sum(values) + tax}
async def greet(name: str):
    return "Hello " + name
'''


async def exercise(target, mode="auto"):
    async with Client(target, mode=mode, read_timeout_seconds=10) as client:
        assert client.protocol_version == (
            "2025-11-25" if mode == "legacy" else "2026-07-28"
        )
        tools = (await client.list_tools()).tools
        assert [t.name for t in tools] == ["greet", "total"]
        assert all(t.annotations is None for t in tools)
        result = await client.call_tool("total", {"values": [1, 2], "tax": 3})
        assert result.structured_content == {"total": 6}
        assert not result.is_error
        if mode != "legacy":
            assert (
                await client.call_tool("greet", {"name": "Ada"})
            ).structured_content == "Hello Ada"
        invalid = await client.call_tool("total", {"values": ["bad"]})
        assert invalid.is_error and invalid.content[0].text == "Invalid tool arguments"


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_generated_stdio_with_official_client(tmp_path, mode):
    root = tmp_path / "bundle"
    generate(inspect_source(SOURCE, module_name="transport_sample"), SOURCE, root)
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(root / "server.py"), "--transport", "stdio"],
        cwd=root,
    )
    anyio.run(exercise, params, mode)


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_generated_streamable_http_with_official_client(tmp_path, mode):
    root = tmp_path / "bundle"
    generate(inspect_source(SOURCE, module_name="transport_sample"), SOURCE, root)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with (tmp_path / "server.log").open("w+") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                str(root / "server.py"),
                "--transport",
                "streamable-http",
                "--port",
                str(port),
            ],
            cwd=root,
            stdout=log,
            stderr=log,
        )
        try:
            url = f"http://127.0.0.1:{port}/mcp"
            deadline = time.monotonic() + 15
            while True:
                try:
                    response = httpx2.get(url, timeout=0.3)
                    if response.status_code < 500:
                        break
                except httpx2.HTTPError:
                    pass
                assert process.poll() is None, (root / "server.py").read_text()
                assert time.monotonic() < deadline, (
                    "Generated HTTP server did not start"
                )
                time.sleep(0.05)
            anyio.run(exercise, url, mode)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_runtime_cli_selects_sdk_transport_without_changing_contract(
    tmp_path, monkeypatch
):
    from apizr.generators.mcp import runtime

    root = tmp_path / "bundle"
    generate(inspect_source(SOURCE, module_name="transport_config"), SOURCE, root)
    calls = []

    class Server:
        def streamable_http_app(self, **kwargs):
            calls.append(("http", kwargs))
            return self

    async def stdio(server):
        calls.append(("stdio", server))

    server = Server()
    monkeypatch.setattr(runtime, "__file__", str(root / "server.py"))
    monkeypatch.setattr(runtime, "create_server", lambda root, plan: server)
    monkeypatch.setattr(runtime, "serve_stdio", stdio)
    monkeypatch.setattr(
        runtime.uvicorn, "run", lambda app, **kw: calls.append(("run", kw))
    )
    for transport in ("stdio", "streamable-http"):
        monkeypatch.setattr(
            sys, "argv", ["server.py", "--transport", transport, "--port", "9001"]
        )
        runtime.main()
    assert calls == [
        ("stdio", server),
        ("http", {"host": "127.0.0.1"}),
        ("run", {"host": "127.0.0.1", "port": 9001}),
    ]
    assert (
        json.loads((root / "apizr-mcp.json").read_bytes())["protocol"]["target"]
        == "2026-07-28"
    )
