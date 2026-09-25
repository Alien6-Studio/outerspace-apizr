import io
import json
from types import SimpleNamespace

import pytest
from apizr_mcp import __main__ as entry
from apizr_mcp import server, worker
from apizr_mcp.model import Job, PlanArguments


def wire(arguments, operation="calculate"):
    return json.dumps(
        {
            "protocol": "apizr.extension/v1",
            "request_id": "a" * 32,
            "operation": operation,
            "arguments": arguments,
        }
    ).encode()


@pytest.mark.parametrize("raw", [b"not JSON", b"x" * 1048577, b"{}"])
def test_malformed_private_worker_requests(raw, monkeypatch, capsys):
    monkeypatch.setattr(worker.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(raw)))
    assert worker.main() == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("case", ["valid", "invalid", "unknown", "missing-root"])
def test_worker_protocol_results(project, monkeypatch, capsys, case):
    _, scope = project
    args = Job(
        scope=scope, arguments=PlanArguments(), operation="readiness"
    ).model_dump(mode="json")
    if case == "invalid":
        args["scope"]["unknown"] = True
    if case == "missing-root":
        args["scope"]["root"] = "/no-such-apizr-root"
    monkeypatch.setattr(
        worker.sys,
        "stdin",
        SimpleNamespace(
            buffer=io.BytesIO(
                wire(args, "unknown" if case == "unknown" else "calculate")
            )
        ),
    )
    assert worker.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["request_id"] == "a" * 32
    assert result["result"]["ok"] == (case == "valid")


def test_package_entrypoints(monkeypatch):
    monkeypatch.setattr(
        server, "main", lambda args: 21 if args == ["--project", "/demo"] else 0
    )
    monkeypatch.setattr(worker, "main", lambda: 22)
    monkeypatch.setattr(entry.sys, "argv", ["apizr_mcp", "serve", "--project", "/demo"])
    assert entry.main() == 21
    monkeypatch.setattr(entry.sys, "argv", ["apizr_mcp"])
    assert entry.main() == 22
