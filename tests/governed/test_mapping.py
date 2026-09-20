import sys

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp import Client

from apizr.execution.model import ExecutionResult
from apizr.governed import bootstrap, mcp, rest
from apizr.governed.runtime import GovernedRuntime

from .helpers import bundle

pytestmark = pytest.mark.timeout(30)


@pytest.mark.parametrize(
    "status",
    [
        "invalid_input",
        "timeout",
        "worker_failed",
        "binding_failed",
        "policy_refused",
        "result_invalid",
        "execution_failed",
        "output_limit",
        "source_mismatch",
    ],
)
def test_failure_mapping_is_explicit_and_sanitized(tmp_path, monkeypatch, status):
    root = bundle(tmp_path / "rest", "rest", source=b"def f(): return 1")
    monkeypatch.setattr(
        GovernedRuntime, "invoke", lambda *args: ExecutionResult(status=status)
    )
    with TestClient(rest.create_app(root)) as client:
        response = client.post("/capabilities/f", json={})
        assert response.status_code == {"invalid_input": 422, "timeout": 504}.get(
            status, 500
        )
        assert response.json() == {
            "detail": {
                "invalid_input": "Invalid request arguments",
                "timeout": "Execution timed out",
            }.get(status, "Internal server error")
        }
        assert client.get("/health").json() == {"status": "ok"}
        assert client.post("/capabilities/f", content=b"not json").status_code == 422
    root = bundle(tmp_path / "mcp", "mcp", source=b"def f(): return 1")

    async def check():
        async with Client(mcp.create_server(root)) as client:
            assert len((await client.list_tools()).tools) == 1
            result = await client.call_tool("f", {})
            assert result.is_error
            assert result.content[0].text == {
                "invalid_input": "Invalid tool arguments",
                "timeout": "Tool execution timed out",
            }.get(status, "Tool execution failed")
            assert (await client.call_tool("missing", {})).content[
                0
            ].text == "Unknown tool"

    anyio.run(check)


def test_bootstrap_and_mcp_cli_use_only_explicit_bundle(tmp_path, monkeypatch):
    root = bundle(tmp_path / "bundle", "mcp", source=b"def f(): return 1")
    before = set(sys.modules)
    try:
        bootstrap.activate(root)
        assert "apizr_governed" in sys.modules
        assert "governed_sample" not in sys.modules
    finally:
        for name in set(sys.modules) - before:
            if name.startswith("apizr_governed"):
                sys.modules.pop(name, None)
    monkeypatch.setattr(
        bootstrap.importlib.util, "spec_from_file_location", lambda *args, **kw: None
    )
    with pytest.raises(RuntimeError, match="runtime unavailable"):
        bootstrap.activate(root)
    calls = []
    server = mcp.create_server(root)
    monkeypatch.setattr(mcp, "create_server", lambda root: server)

    async def stdio(server):
        calls.append("stdio")

    monkeypatch.setattr(mcp, "serve_stdio", stdio)
    monkeypatch.setattr(mcp.uvicorn, "run", lambda app, **kw: calls.append(kw))
    for mode in ["stdio", "streamable-http"]:
        monkeypatch.setattr(sys, "argv", ["server.py", "--transport", mode])
        mcp.main(root)
    assert calls == ["stdio", {"host": "127.0.0.1", "port": 8000}]
