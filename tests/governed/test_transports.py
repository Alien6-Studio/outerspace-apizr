import json
import os
import sys
import time

import anyio
import httpx
import pytest
from mcp import Client, StdioServerParameters

from apizr.execution import ExecutionPolicy

from .helpers import SERVER, bundle, http_server

pytestmark = pytest.mark.timeout(60)


def test_real_governed_rest_survives_failures_and_tampering(tmp_path, monkeypatch):
    monkeypatch.setenv("APIZR_TEST_SECRET", "super-secret")
    root = bundle(
        tmp_path / "rest",
        "rest",
        policy=ExecutionPolicy.model_validate(
            {"limits": {"wall_time_ms": 1000, "max_output_bytes": 256}}
        ),
    )
    with (
        http_server(root, "rest") as (url, process),
        httpx.Client(base_url=url, timeout=8) as client,
    ):

        def call(name, args=None):
            return client.post(
                "/capabilities/" + name, json={} if args is None else args
            )

        assert call("total", {"a": 1}).json() == 6
        assert call("greet", {"name": "Ada"}).json() == "Hello Ada"
        assert call("nullable").json() is None
        assert call("default_null").json() is None
        assert call("default_null", {"x": None}).status_code == 422
        assert call("total", {"a": True}).status_code == 422
        assert call("total", {"a": 1, "extra": 0}).status_code == 422
        assert call("counter").json() == call("counter").json() == [1, 1]
        assert call("environment").json() is False
        assert call("pid").json() != process.pid
        for name in ["loop", "sleep", "crash", "fail", "large"]:
            start = time.monotonic()
            response = call(name, {"n": 500} if name == "large" else {})
            assert response.status_code == (504 if name in ["loop", "sleep"] else 500)
            assert time.monotonic() - start < 6
            assert response.json() == {
                "detail": "Execution timed out"
                if name in ["loop", "sleep"]
                else "Internal server error"
            }
            assert call("total", {"a": 1}).json() == 6
        source = root / "source/governed_sample.py"
        original = source.read_bytes()
        source.write_bytes(original + b'\nraise RuntimeError("must not import")')
        assert call("total", {"a": 1}).status_code == 500
        source.write_bytes(original)
        assert call("total", {"a": 1}).json() == 6
        for path in [
            "execution/policy.json",
            "execution/plans/total.json",
            "execution/worker.py",
        ]:
            target = root / path
            original = target.read_bytes()
            target.unlink()
            assert call("total", {"a": 1}).json() == {"detail": "Internal server error"}
            target.write_bytes(original)
            assert call("total", {"a": 1}).json() == 6


async def exercise_mcp(target, root, history):
    async with Client(target, read_timeout_seconds=8) as client:
        assert client.protocol_version == "2026-07-28"

        async def call(name, args=None):
            # Test-owned names/timings only: retain the preceding failure and the
            # recovery attempt in JUnit even when an ExceptionGroup hides locals.
            event = {"tool": name, "outcome": "exception"}
            started = time.monotonic()
            try:
                result = await client.call_tool(name, {} if args is None else args)
                event["outcome"] = "error" if result.is_error else "success"
                if result.is_error:
                    text = (
                        getattr(result.content[0], "text", "") if result.content else ""
                    )
                    event["error"] = (
                        text
                        if text
                        in {
                            "Invalid tool arguments",
                            "Tool execution timed out",
                            "Tool execution failed",
                        }
                        else "unexpected_tool_error"
                    )
                return result
            finally:
                event["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
                history.append(event)

        assert (await call("total", {"a": 1})).structured_content == 6
        assert (await call("greet", {"name": "Ada"})).structured_content == "Hello Ada"
        assert (await call("nullable")).structured_content is None
        assert not (await call("default_null")).is_error
        for name, args in [
            ("total", {}),
            ("default_null", {"x": None}),
            ("total", {"a": 1, "extra": 0}),
        ]:
            invalid = await call(name, args)
            assert (
                invalid.is_error and invalid.content[0].text == "Invalid tool arguments"
            )
        assert (
            (await call("counter")).structured_content
            == (await call("counter")).structured_content
            == [1, 1]
        )
        assert (await call("environment")).structured_content is False
        for name in ["loop", "sleep", "crash", "fail", "large"]:
            start = time.monotonic()
            response = await call(name, {"n": 500} if name == "large" else {})
            assert response.is_error and time.monotonic() - start < 6
            assert response.content[0].text == (
                "Tool execution timed out"
                if name in ["loop", "sleep"]
                else "Tool execution failed"
            )
            assert (await call("total", {"a": 1})).structured_content == 6
        for path in [
            "source/governed_sample.py",
            "execution/policy.json",
            "execution/plans/total.json",
            "execution/worker.py",
        ]:
            target_path = root / path
            original = target_path.read_bytes()
            target_path.write_bytes(original + b"\nchanged")
            response = await call("total", {"a": 1})
            assert (
                response.is_error
                and response.content[0].text == "Tool execution failed"
            )
            target_path.write_bytes(original)
            assert (await call("total", {"a": 1})).structured_content == 6


@pytest.mark.parametrize("transport", ["stdio", "streamable-http"])
def test_real_governed_mcp_survives_failures(tmp_path, monkeypatch, transport, request):
    monkeypatch.setenv("APIZR_TEST_SECRET", "super-secret")
    root = bundle(
        tmp_path / "mcp",
        "mcp",
        policy=ExecutionPolicy.model_validate(
            {"limits": {"wall_time_ms": 1000, "max_output_bytes": 256}}
        ),
    )
    history = []
    try:
        if transport == "stdio":
            params = StdioServerParameters(
                command=sys.executable,
                args=["-I", "-c", SERVER, str(root), "stdio"],
                cwd=root,
                env=dict(os.environ),
            )
            anyio.run(exercise_mcp, params, root, history)
        else:
            with http_server(root, "mcp") as (url, _):
                anyio.run(exercise_mcp, url + "/mcp", root, history)
    finally:
        request.node.user_properties.append(("mcp_call_history", json.dumps(history)))
