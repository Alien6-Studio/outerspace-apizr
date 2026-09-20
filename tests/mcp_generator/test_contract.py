import json
from hashlib import sha256

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp import Client
from rest.helpers import application

from apizr.generators.mcp import render
from apizr.generators.mcp.model import Manifest
from apizr.generators.mcp.planner import tool_name
from apizr.generators.rest import render as rest_render
from apizr.inspection import inspect_source

from .helpers import server_bundle


@pytest.mark.parametrize(
    ("annotation", "value"),
    [
        ("int", 3),
        ("float", 2.5),
        ("str", "hi"),
        ("bool", True),
        ("None", None),
        ("Any", {"x": [True, None, 3]}),
        ("list[int]", [2]),
        ("dict[str,int]", {"x": 3}),
        ("tuple[int,str]", [2, "a"]),
        ("tuple[int,...]", [1, 2]),
        ("set[int]", [1]),
        ("int | str", "a"),
        ("Union[int,str]", 2),
        ("Optional[int]", None),
        ("Literal['a','b']", "b"),
        ("tuple[()]", []),
        ("list", [None]),
        ("dict", {}),
    ],
)
def test_schema_and_invocation_agree_across_backends(tmp_path, annotation, value):
    source = f"from __future__ import annotations\ndef f(x: {annotation}, /, *, option: int | None = 1): return {{'kind': type(x).__name__, 'option': option}}\n".encode()
    inspection = inspect_source(source, module_name="cross")
    rest = json.loads(rest_render(inspection, source)["openapi.json"])
    mcp = json.loads(render(inspection, source)["mcp-tools.json"])
    schema = rest["paths"]["/capabilities/f"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert schema == mcp["tools"][0]["inputSchema"]

    async def check(server, expected):
        async with Client(server) as client:
            assert client.protocol_version == "2026-07-28"
            capabilities = client.server_capabilities
            assert capabilities.tools is not None
            assert (
                capabilities.resources
                is capabilities.prompts
                is capabilities.extensions
                is None
            )
            tool = (await client.list_tools()).tools[0]
            assert tool.input_schema == schema
            assert tool.annotations is None and tool.output_schema is None
            for arguments, result in expected:
                actual = await client.call_tool("f", arguments)
                assert not actual.is_error
                assert actual.structured_content == result

    with application(tmp_path / "rest", source) as adapter:
        http = TestClient(adapter.app)
        expected = [
            (args, http.post("/capabilities/f", json=args).json())
            for args in [{"x": value}, {"x": value, "option": None}]
        ]
    with server_bundle(tmp_path / "mcp", source) as (server, _):
        anyio.run(check, server, expected)


def test_names_descriptions_and_manifest(tmp_path):
    source = b'def f(x: int):\n    """Source documentation."""\n    return x\n'
    inspection = inspect_source(source, module_name="project.pricing")
    artifacts = render(inspection, source)
    manifest = Manifest.model_validate_json(artifacts["apizr-mcp.json"])
    assert manifest.schema_version == "apizr.mcp/v1"
    assert manifest.protocol.target == "2026-07-28"
    assert manifest.protocol.sdk == "mcp>=2.2,<3"
    assert "source/project/__init__.py" in artifacts
    assert "apizr-mcp.json" not in manifest.artifacts
    assert set(manifest.artifacts) == set(artifacts) - {"apizr-mcp.json"}
    for name, digest in manifest.artifacts.items():
        assert digest.value == sha256(artifacts[name]).hexdigest()
    tool = json.loads(artifacts["mcp-tools.json"])["tools"][0]
    assert tool["name"] == "f" and tool["description"] == "Source documentation."
    assert (
        tool["_meta"]["sh.outerspace.apizr/capability-id"] == "python:project.pricing:f"
    )
    assert b"fastapi" not in artifacts["requirements.txt"]
    assert b"apizr.interfaces" not in artifacts["server.py"]
    for symbol in ["écho", "a" * 100, "apizr_reserved"]:
        name = tool_name("python:p:" + symbol, symbol)
        assert name == "apizr_" + sha256(("python:p:" + symbol).encode()).hexdigest()
    assert tool_name("python:p:f", "f") == "f"


def test_tool_name_hash_collision_is_refused(monkeypatch):
    from apizr.generators.mcp import planner

    monkeypatch.setattr(planner, "tool_name", lambda *args: "same")
    source = b"def a(): pass\ndef b(): pass"
    with pytest.raises(ValueError, match="collision"):
        render(inspect_source(source, module_name="collision"), source)
