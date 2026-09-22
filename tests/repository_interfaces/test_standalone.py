"""Execute emitted artifacts, including both SDK transports, without apizr imports."""

import socket
import subprocess
import sys
import time

import anyio
import httpx
import httpx2
from governed.helpers import SERVER, http_server
from mcp import Client, StdioServerParameters

from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.output import write_bundle


async def exercise(target):
    async with Client(target, read_timeout_seconds=10) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
        assert names == {"shop.api.run", "shop.pricing.run", "shop.inventory.available"}
        assert (await client.call_tool("shop.api.helper", {})).is_error
        assert (await client.call_tool("shop.api.run", {})).structured_content == 7
        assert (
            await client.call_tool("shop.pricing.run", {"x": 4})
        ).structured_content == 5


def test_emitted_rest_no_apizr_dependency(tmp_path, inputs):
    write_bundle(tmp_path, render_repository_bundle(*inputs, interface="rest"))
    probe = """import sys
sys.path.insert(0, sys.argv[1])
def audit(event, args):
 if event == "import" and args[0].startswith("apizr."): raise AssertionError("apizr dependency")
sys.addaudithook(audit)
from app import app
from fastapi.testclient import TestClient
with TestClient(app) as client:
 assert client.post("/capabilities/shop.api.run", json={}).json() == 7
 assert client.post("/capabilities/shop.pricing.run", json={"x":4}).json() == 5
assert "shop.admin" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe, str(tmp_path)],
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode()


def test_emitted_direct_rest_real_server(tmp_path, inputs, monkeypatch):
    write_bundle(tmp_path, render_repository_bundle(*inputs, interface="rest"))
    # Match the documented uvicorn --app-dir startup while using the shared
    # bounded server lifecycle. Direct source import is deliberately permitted.
    monkeypatch.setattr(
        "governed.helpers.SERVER",
        SERVER.replace(
            "root=Path(sys.argv[1]).resolve()",
            "root=Path(sys.argv[1]).resolve()\nsys.path.insert(0,str(root))",
        ),
    )
    with http_server(tmp_path, "rest") as (url, process):
        with httpx.Client(base_url=url, timeout=10) as client:
            assert client.post("/capabilities/shop.api.run", json={}).json() == 7
            assert (
                client.post("/capabilities/shop.pricing.run", json={"x": 4}).json() == 5
            )
            assert (
                client.post("/capabilities/shop.api.helper", json={}).status_code == 404
            )
            assert (
                "/capabilities/shop.api.helper"
                not in client.get("/openapi.json").json()["paths"]
            )
            assert process.poll() is None


def test_emitted_mcp_stdio(tmp_path, inputs):
    write_bundle(tmp_path, render_repository_bundle(*inputs, interface="mcp"))
    anyio.run(
        exercise,
        StdioServerParameters(
            command=sys.executable, args=[str(tmp_path / "server.py")], cwd=tmp_path
        ),
    )


def test_emitted_mcp_streamable_http(tmp_path, inputs):
    write_bundle(tmp_path, render_repository_bundle(*inputs, interface="mcp"))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with (tmp_path / "server.log").open("w+") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                str(tmp_path / "server.py"),
                "--transport",
                "streamable-http",
                "--port",
                str(port),
            ],
            cwd=tmp_path,
            stdout=log,
            stderr=log,
        )
        try:
            url = f"http://127.0.0.1:{port}/mcp"
            deadline = time.monotonic() + 15
            while True:
                try:
                    if httpx2.get(url, timeout=0.3).status_code < 500:
                        break
                except httpx2.HTTPError:
                    pass
                assert process.poll() is None
                assert time.monotonic() < deadline
                time.sleep(0.05)
            anyio.run(exercise, url)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_mcp_entry_point_and_stdio_lifecycle(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager

    from apizr.repository_interfaces import mcp_runtime as runtime

    calls = []

    class Server:
        def streamable_http_app(self, **kwargs):
            calls.append(("http", kwargs))
            return self

        def create_initialization_options(self):
            return "options"

        async def run(self, read, write, options):
            calls.append((read, write, options))

    @asynccontextmanager
    async def stdio():
        yield "read", "write"

    monkeypatch.setattr(runtime, "stdio_server", stdio)
    monkeypatch.setattr(runtime, "create_server", lambda *args: Server())
    monkeypatch.setattr(
        runtime.uvicorn, "run", lambda app, **kwargs: calls.append(("run", kwargs))
    )
    for transport in ("stdio", "streamable-http"):
        monkeypatch.setattr(
            sys, "argv", ["server.py", "--transport", transport, "--port", "9001"]
        )
        runtime.main()
    assert calls == [
        ("read", "write", "options"),
        ("http", {"host": "127.0.0.1"}),
        ("run", {"host": "127.0.0.1", "port": 9001}),
    ]
