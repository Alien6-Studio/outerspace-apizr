import sys

import anyio
import pytest
from mcp import Client

from .helpers import server_bundle


@pytest.mark.parametrize(
    ("source", "arguments", "expected"),
    [
        ("def f(a: int, /, b: int = 2, *, c: int = 3): return a+b+c", {"a": 1}, 6),
        ("async def f(x: int): return x+1", {"x": 2}, 3),
        (
            "def f() -> int: return {'actual':'not an integer'}",
            {},
            {"actual": "not an integer"},
        ),
        ("def f(): return [1,True,None]", {}, [1, True, None]),
        ("def f(): return None", {}, None),
        ("def f(): return 'hello'", {}, "hello"),
        ("def f(): return True", {}, True),
    ],
)
def test_sync_async_and_structured_results(tmp_path, source, arguments, expected):
    async def check(server):
        async with Client(server) as client:
            result = await client.call_tool("f", arguments)
            assert not result.is_error
            assert result.structured_content == expected
            assert (await client.list_tools()).tools[0].description is None

    with server_bundle(tmp_path / "bundle", source) as (server, _):
        anyio.run(check, server)


@pytest.mark.parametrize(
    ("source", "payload"),
    [
        ("def f(x: int): return x", {}),
        ("def f(x: int): return x", {"x": 1, "extra": 3}),
        ("def f(x: int = None): return x", {"x": None}),
        ("def f(x: int): return x", {"x": True}),
        ("def f(a: int = 1,b: int = 2,/): return a+b", {"b": 5}),
        ("def f(x: set[int]): return 1", {"x": [1, 1]}),
        ("def f(x: tuple[int,str]): return 1", {"x": [1]}),
    ],
)
def test_invalid_arguments_are_tool_errors(tmp_path, source, payload):
    async def check(server):
        async with Client(server) as client:
            result = await client.call_tool("f", payload)
            assert result.is_error
            assert result.content[0].text == "Invalid tool arguments"
            unknown = await client.call_tool("missing", {})
            assert unknown.is_error and unknown.content[0].text == "Unknown tool"

    with server_bundle(tmp_path / "bundle", source) as (server, _):
        anyio.run(check, server)


@pytest.mark.parametrize(
    "body",
    [
        "raise RuntimeError('secret /local/path')",
        "return object()",
        "return {1:'key'}",
        "return float('nan')",
        "return (1,2)",
        "return {1,2}",
    ],
)
def test_exceptions_and_non_json_results_are_sanitized(tmp_path, body):
    async def check(server):
        async with Client(server) as client:
            result = await client.call_tool("f", {})
            assert result.is_error and result.structured_content is None
            assert result.content[0].text == "Tool execution failed"

    with server_bundle(tmp_path / "bundle", "def f(): " + body) as (server, _):
        anyio.run(check, server)


def test_omitted_mutable_default_keeps_identity_and_state(tmp_path):
    async def check(server):
        async with Client(server) as client:
            assert (await client.call_tool("f", {})).structured_content == [1]
            assert (await client.call_tool("f", {})).structured_content == [1, 1]
            result = await client.call_tool("f", {"x": None})
            assert result.is_error

    with server_bundle(
        tmp_path / "bundle", "def f(x: list[int] = []):\n    x.append(1)\n    return x"
    ) as (server, _):
        anyio.run(check, server)
        assert sys.modules["mcp_sample"].f.__defaults__[0] == [1, 1]


def test_no_annotation_evaluation_after_import(tmp_path):
    source = "from __future__ import annotations\ndef f(x: int): return x"
    with server_bundle(tmp_path / "bundle", source) as (_, plan):
        from apizr.interfaces.runtime import verify_binding

        fn = sys.modules["mcp_sample"].f
        fn.__annotations__ = {"x": "raise_if_evaluated()"}
        assert verify_binding(sys.modules["mcp_sample"], plan["tools"][0]) is fn


def test_http_exception_has_no_special_mcp_semantics(tmp_path):
    from fastapi import HTTPException

    async def check(server):
        async with Client(server) as client:
            result = await client.call_tool("f", {})
            assert result.is_error and result.content[0].text == "Tool execution failed"

    with server_bundle(
        tmp_path / "bundle", "def f(): raise RuntimeError('private')"
    ) as (server, _):
        # Replace a runtime dependency after trusted import, preserving the bound
        # function's signature and execution form. Generation does not import FastAPI.
        sys.modules["mcp_sample"].f.__globals__["RuntimeError"] = lambda message: (
            HTTPException(418, message)
        )
        anyio.run(check, server)
