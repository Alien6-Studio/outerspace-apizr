"""MCP reuses the editor operations and the canonical store/diff authorities."""

import json
from pathlib import Path

import anyio
import pytest
from apizr_mcp import worker
from apizr_mcp.model import HistoryJob
from mcp import Client
from test_editor_contract import policy, tree
from test_server import setup
from test_worker_protocol import wire

from apizr import tracking
from apizr.editor_contracts.model import EditorRequest
from apizr.experiments.comparison import compare_runs
from apizr.experiments.history import list_runs
from apizr.experiments.store import DEFAULT_STORE
from apizr.workspace.mcp_session import history_scope


def prepared(project):
    path, scope = project
    root = Path(scope.root)
    with tracking.session(root=root) as a:
        tracking.log_parameter("rate", 0.1)
        tracking.log_metric("score", 0.8)
    with tracking.session(root=root) as b:
        tracking.log_parameter("rate", 0.2)
        tracking.log_metric("score", 0.9)
    scope = scope.model_copy(update={"operator_policy": policy(root)})
    return path, scope, a.record, b.record


def test_real_sdk_history_tools_return_canonical_producer_evidence(
    project, monkeypatch
):
    path, scope, a, b = prepared(project)
    _, app = setup((path, scope), monkeypatch)
    before = tree(Path(scope.root))

    async def exercise():
        async with Client(app) as client:
            listing = await client.call_tool("apizr_experiment_list", {})
            assert not listing.is_error
            assert listing.structured_content == list_runs(
                Path(scope.root) / DEFAULT_STORE, include_values=True
            ).model_dump(mode="json")
            shown = await client.call_tool(
                "apizr_experiment_show", {"run_id": a.run_digest[:12]}
            )
            assert not shown.is_error and shown.structured_content == a.model_dump(
                mode="json"
            )
            difference = await client.call_tool(
                "apizr_experiment_diff", {"run_a": a.run_digest, "run_b": b.run_digest}
            )
            assert (
                not difference.is_error
                and difference.structured_content
                == compare_runs(a, b).model_dump(mode="json")
            )
            missing = await client.call_tool(
                "apizr_experiment_show", {"run_id": "f" * 64}
            )
            assert (
                missing.is_error
                and missing.structured_content["error"]["code"] == "run_not_found"
            )
            for tool in (await client.list_tools()).tools:
                if tool.name.startswith("apizr_experiment_"):
                    assert (
                        tool.annotations.read_only_hint
                        and tool.annotations.idempotent_hint
                    )
                    assert not tool.annotations.open_world_hint

    anyio.run(exercise)
    assert before == tree(Path(scope.root))


def test_corrupt_records_are_never_hidden_by_a_display_filter(project, monkeypatch):
    path, scope, a, _ = prepared(project)
    record = Path(scope.root) / DEFAULT_STORE / "runs" / (a.run_digest + ".json")
    record.write_bytes(record.read_bytes() + b" ")
    _, app = setup((path, scope), monkeypatch)

    async def exercise():
        async with Client(app) as client:
            reply = await client.call_tool(
                "apizr_experiment_list", {"status": "failed", "limit": 1}
            )
            assert (
                reply.is_error
                and reply.structured_content["error"]["code"] == "history_invalid"
            )

    anyio.run(exercise)


def test_analysis_authority_alone_cannot_read_history(project, monkeypatch):
    _, app = setup(project, monkeypatch)

    async def exercise():
        async with Client(app) as client:
            result = await client.call_tool("apizr_experiment_list", {})
            assert result.is_error
            assert (
                result.structured_content["error"]["code"]
                == "operator_operation_denied"
            )

    anyio.run(exercise)


@pytest.mark.parametrize(
    "arguments",
    [
        {"store": "/tmp"},
        {"limit": True},
        {"source": "../outside.py"},
        {"operator_policy": {}},
    ],
)
def test_history_arguments_cannot_select_storage_or_authority(
    project, monkeypatch, arguments
):
    _, app = setup(project, monkeypatch)

    async def exercise():
        async with Client(app) as client:
            result = await client.call_tool("apizr_experiment_list", arguments)
            assert (
                result.is_error
                and result.structured_content["error"]["code"] == "invalid_arguments"
            )

    anyio.run(exercise)


def test_private_worker_uses_the_same_history_request_contract(
    project, monkeypatch, capsys
):
    import io
    from types import SimpleNamespace

    _, scope, a, _ = prepared(project)
    job = HistoryJob(
        scope=history_scope(scope),
        request=EditorRequest.model_validate(
            {"operation": "experiment_show", "arguments": {"run_id": a.run_digest}}
        ),
    )
    monkeypatch.setattr(
        worker.sys,
        "stdin",
        SimpleNamespace(
            buffer=io.BytesIO(wire(job.model_dump(mode="json"), "history"))
        ),
    )
    assert worker.main() == 0
    response = json.loads(capsys.readouterr().out)
    assert response["result"]["ok"] and response["result"]["value"] == a.model_dump(
        mode="json"
    )


@pytest.mark.parametrize("operation", ["capabilities", "inspect", "plan_exposure"])
def test_history_worker_refuses_non_history_operations(project, operation):
    _, scope = project
    arguments = {"source": "train.py"} if operation == "inspect" else {}
    with pytest.raises(ValueError, match="history_operation_invalid"):
        HistoryJob(
            scope=history_scope(scope),
            request=EditorRequest.model_validate(
                {"operation": operation, "arguments": arguments}
            ),
        )
