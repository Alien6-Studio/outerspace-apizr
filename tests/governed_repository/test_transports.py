import json
import os
import sys

import anyio
import httpx
import pytest
from governed.helpers import SERVER, http_server
from governed_oci.test_transports import damage, remaining
from mcp import Client, StdioServerParameters

from apizr.execution.policy import ExecutionPolicy
from apizr.oci.model import ExecutionPolicyV2

from .helpers import bundle

pytestmark = pytest.mark.timeout(180)
AUDITED = SERVER.replace(
    '    if event=="exec" and "/source/" in str(args[0].co_filename):',
    '    if event=="import" and (args[0]=="sample" or args[0].startswith("sample.")):\n'
    '        raise RuntimeError("project import in transport")\n'
    '    if event=="exec" and ("/source/" in str(args[0].co_filename) or str(args[0].co_filename).startswith("<apizr-repository:")):',
)


@pytest.mark.parametrize("backend", ["local-process", "oci-container"])
@pytest.mark.parametrize("transport", ["rest", "stdio", "streamable-http"])
def test_real_multisource_transports(
    tmp_path, monkeypatch, request, backend, transport
):
    image = (
        request.getfixturevalue("worker_image") if backend == "oci-container" else None
    )
    policy = (ExecutionPolicyV2 if image else ExecutionPolicy).model_validate(
        {"limits": {"wall_time_ms": 2000, "max_output_bytes": 1024}}
    )
    monkeypatch.setenv("APIZR_TEST_SECRET", "secret-parent-only")
    monkeypatch.setattr("governed.helpers.SERVER", AUDITED)
    root = bundle(
        tmp_path / "bundle",
        "rest" if transport == "rest" else "mcp",
        policy=policy,
        image=image,
    )
    before = remaining() if image else None
    bridge = json.loads((root / "execution/bundle.json").read_bytes())
    paths = [
        "source/sample/api.py",
        "source/sample/pricing.py",
        "execution/policy.json",
        "repository-interface.json",
        "execution/worker.py",
        "execution/bundle.json",
        bridge["capabilities"]["python:sample.api:run"]["path"],
    ]
    cases = [
        ("sample.api.run", {}, 4),
        ("sample.pricing.run", {"x": 4}, 5),
        ("sample.api.counter", {}, [1, 1, 1]),
        ("sample.api.counter", {}, [1, 1, 1]),
        ("sample.api.environment", {}, False),
    ]
    failures = [
        ("run", {"a": True}, 422, "Invalid tool arguments"),
        ("loop", {}, 504, "Tool execution timed out"),
        ("crash", {}, 500, "Tool execution failed"),
        ("fail", {}, 500, "Tool execution failed"),
        ("large", {"n": 2000}, 500, "Tool execution failed"),
    ]
    if transport == "rest":
        with (
            http_server(root, "rest") as (url, process),
            httpx.Client(base_url=url, timeout=20) as client,
        ):

            def call(name, args):
                return client.post("/capabilities/" + name, json=args)

            routes = client.get("/openapi.json").json()["paths"]
            assert "/capabilities/sample.pricing.double" not in routes
            for name, args, expected in cases:
                response = call(name, args)
                assert response.status_code == 200 and response.json() == expected, (
                    response.text
                )
            for name, args, status, _ in failures:
                response = call("sample.api." + name, args)
                assert response.status_code == status and "SECRET" not in response.text
                assert call("sample.api.run", {}).json() == 4
            for path in paths:
                target, original = damage(root, path)
                assert call("sample.api.run", {}).status_code == 500
                target.write_bytes(original)
                assert call("sample.api.run", {}).json() == 4
            assert process.poll() is None
    else:

        async def check(connection):
            async with Client(connection, read_timeout_seconds=20) as client:
                names = [t.name for t in (await client.list_tools()).tools]
                assert len(names) == 8 and "sample.pricing.double" not in names
                for name, args, expected in cases:
                    response = await client.call_tool(name, args)
                    assert (
                        not response.is_error
                        and response.structured_content == expected
                    ), response
                for name, args, _, message in failures:
                    response = await client.call_tool("sample.api." + name, args)
                    assert response.is_error and response.content[0].text == message
                    assert (
                        await client.call_tool("sample.api.run", {})
                    ).structured_content == 4
                for path in paths:
                    target, original = damage(root, path)
                    assert (await client.call_tool("sample.api.run", {})).content[
                        0
                    ].text == "Tool execution failed"
                    target.write_bytes(original)
                    assert (
                        await client.call_tool("sample.api.run", {})
                    ).structured_content == 4

        if transport == "stdio":
            anyio.run(
                check,
                StdioServerParameters(
                    command=sys.executable,
                    args=["-I", "-c", AUDITED, str(root), "stdio"],
                    cwd=root,
                    env=dict(os.environ),
                ),
            )
        else:
            with http_server(root, "mcp") as (url, process):
                anyio.run(check, url + "/mcp")
                assert process.poll() is None
    if image:
        assert remaining() == before
