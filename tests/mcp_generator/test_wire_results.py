"""Assert MCP objects on the wire, without the SDK's permissive result model."""

import asyncio
import json
import sys

import pytest
from repository_interfaces.conftest import evidence

from apizr.execution import ExecutionPolicy
from apizr.generators.mcp import generate
from apizr.inspection import inspect_source
from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.output import write_bundle

SOURCE = b"""def quote(unit_price: float, quantity: int): return unit_price * quantity
def available(stock: int, requested: int): return stock >= requested
def items(): return [1, True, None, {"nested": [2]}]
def nothing(): return None
async def greeting(): return "hello"
def object_result(): return {"result": 25.0, "other": [True, None]}
def fail(): raise RuntimeError("private detail")
"""
CASES = [
    ("quote", {"unit_price": 12.5, "quantity": 2}, {"result": 25.0}),
    ("available", {"stock": 10, "requested": 3}, {"result": True}),
    ("items", {}, {"result": [1, True, None, {"nested": [2]}]}),
    ("nothing", {}, {"result": None}),
    ("greeting", {}, {"result": "hello"}),
    ("object_result", {}, {"result": 25.0, "other": [True, None]}),
]


async def exchange(root, prefix):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(root / "server.py"),
        cwd=root,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:

        async def send(message):
            process.stdin.write(
                json.dumps({"jsonrpc": "2.0", **message}).encode() + b"\n"
            )
            await process.stdin.drain()

        async def request(identity, method, params):
            await send({"id": identity, "method": method, "params": params})
            while True:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=15)
                assert line, "Generated server closed stdout before its response"
                message = json.loads(line)
                if message.get("id") == identity:
                    assert "error" not in message, message
                    return message["result"]

        await request(
            0,
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "strict-contract-probe", "version": "1"},
            },
        )
        await send({"method": "notifications/initialized"})
        for identity, (name, arguments, expected) in enumerate(CASES, 1):
            result = await request(
                identity,
                "tools/call",
                {
                    "name": prefix + name,
                    "arguments": arguments,
                },
            )
            assert not result.get("isError", False), result
            # MCP requires an object, even when the SDK accepts other JSON types.
            assert isinstance(result["structuredContent"], dict), result
            assert result["structuredContent"] == expected
            assert len(result["content"]) == 1
            assert result["content"][0]["type"] == "text"
            assert json.loads(result["content"][0]["text"]) == expected
        for identity, name, arguments in [(20, "fail", {}), (21, "quote", {})]:
            result = await request(
                identity,
                "tools/call",
                {
                    "name": prefix + name,
                    "arguments": arguments,
                },
            )
            assert result["isError"] is True
            assert "structuredContent" not in result
            assert "private detail" not in json.dumps(result)
    finally:
        process.stdin.close()
        if process.returncode is None:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await asyncio.wait_for(process.wait(), timeout=5)


@pytest.mark.timeout(90)
@pytest.mark.parametrize("repository", [False, True])
@pytest.mark.parametrize("governed", [False, True])
def test_generated_results_are_objects_on_the_wire(tmp_path, repository, governed):
    root = tmp_path / "bundle"
    policy = ExecutionPolicy() if governed else None
    if repository:
        inputs = evidence(
            {"sample.py": SOURCE},
            selected=tuple("python:sample:" + name for name, _, _ in CASES)
            + ("python:sample:fail",),
            modes=("local-process" if governed else "direct",),
            interfaces=("mcp",),
        )
        write_bundle(
            root,
            render_repository_bundle(*inputs, interface="mcp", execution_policy=policy),
        )
    else:
        generate(
            inspect_source(SOURCE, module_name="sample"),
            SOURCE,
            root,
            execution_policy=policy,
        )
    asyncio.run(exchange(root, "sample." if repository else ""))
