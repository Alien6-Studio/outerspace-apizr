"""Official SDK dispatch keeps one operator-selected delivery behind core authority."""

import json
from pathlib import Path
from threading import Event

import anyio
import pytest
from apizr_mcp import server
from apizr_mcp.model import ServerLimits
from batch_inputs import request
from delivery_batch.test_batch import Managed
from mcp import Client

from apizr.delivery_batch import BatchResult, inspect_batch, operations
from apizr.extension_runtime import CleanupFailed, InvocationCancelled
from apizr.mcp_session import DeliverySession, McpSession


def configured(project, tmp_path, *, count=3, limits=None):
    batch = request(tmp_path, count=count)
    session = McpSession(
        analysis=project[1],
        delivery=DeliverySession(request=batch, plugins_dir=str(tmp_path / "plugins")),
    )
    calculations = server.Calculations(session, limits or ServerLimits())
    return batch, calculations, server.create_server(calculations)


def arguments(batch):
    return {
        "expected_delivery_manifest_digest": batch.build.delivery_manifest_digest.model_dump(
            mode="json"
        )
    }


async def result(client, name, args=None):
    reply = await client.call_tool("apizr_delivery_" + name, args or {})
    assert not reply.is_error, reply
    return BatchResult.model_validate_json(json.dumps(reply.structured_content))


def test_fatal_cleanup_cannot_promote_a_concurrent_delivery_result(
    project, tmp_path, monkeypatch
):
    _, calcs, app = configured(project, tmp_path)
    calls = []

    async def interrupted(operation, expected):
        calls.append(operation)
        calcs.fatal.set()
        return {"ok": True, "value": {}}

    monkeypatch.setattr(calcs, "call_delivery", interrupted)

    async def exercise():
        async with Client(app) as client:
            for _ in range(2):
                reply = await client.call_tool("apizr_delivery_status", {})
                assert reply.is_error
                assert reply.structured_content == {
                    "error": {"code": "cleanup_unconfirmed", "diagnostics": []}
                }
        assert calls == ["status"]

    anyio.run(exercise)


def test_default_discovery_does_not_enable_delivery_from_authority(
    project, monkeypatch
):
    calcs = server.Calculations(project[1], ServerLimits())
    for name in ("deliver_batch", "inspect_batch"):
        monkeypatch.setattr(
            server, name, lambda *a, **k: pytest.fail("delivery accessed")
        )

    async def exercise():
        async with Client(server.create_server(calcs)) as client:
            tools = (await client.list_tools()).tools
            assert [t.name for t in tools] == [
                "apizr_analyze",
                "apizr_readiness",
                "apizr_plan_exposure",
            ]
            assert all(
                t.annotations.read_only_hint and not t.annotations.open_world_hint
                for t in tools
            )
            for name in ["status", "run", "resume"]:
                reply = await client.call_tool("apizr_delivery_" + name, {})
                assert reply.structured_content["error"]["code"] == "unknown_tool"

    anyio.run(exercise)

    async def disabled():
        with pytest.raises(server.DeliveryRefused, match="delivery_not_enabled"):
            await calcs.call_delivery("run", None)

    anyio.run(disabled)


def test_schema_annotations_and_request_cannot_be_replaced(
    project, tmp_path, monkeypatch
):
    batch, calcs, app = configured(project, tmp_path)
    calls = []
    monkeypatch.setattr(server, "deliver_batch", lambda *a, **k: calls.append((a, k)))

    async def exercise():
        async with Client(app) as client:
            tools = (await client.list_tools()).tools
            assert [t.name for t in tools] == [
                t[0] for t in (*server.TOOLS, *server.DELIVERY_TOOLS)
            ]
            for t in tools[3:]:
                assert t.input_schema["additionalProperties"] is False
                effect = t.name != "apizr_delivery_status"
                assert t.annotations.read_only_hint is (not effect)
                assert t.annotations.destructive_hint is False
                assert t.annotations.idempotent_hint is (not effect)
                assert t.annotations.open_world_hint is effect
                assert set(t.input_schema["properties"]) == (
                    {"expected_delivery_manifest_digest"} if effect else set()
                )
            for field in [
                "root",
                "request",
                "delivery_request",
                "evidence_root",
                "plugins_dir",
                "operator_policy",
                "docker",
                "authentication",
                "key_file",
                "tsa_url",
                "trust_store",
                "destination",
                "recovery_reference",
                "selected_artifact",
                "plugin",
                "operation",
            ]:
                reply = await client.call_tool(
                    "apizr_delivery_run", arguments(batch) | {field: "PRIVATE"}
                )
                assert reply.structured_content["error"]["code"] == "invalid_arguments"
                assert "PRIVATE" not in reply.model_dump_json()
            wrong = {
                "expected_delivery_manifest_digest": {
                    "algorithm": "sha256",
                    "value": "f" * 64,
                }
            }
            for name in ("run", "resume"):
                reply = await client.call_tool("apizr_delivery_" + name, wrong)
                assert (
                    reply.structured_content["error"]["code"]
                    == "delivery_identity_changed"
                )
            absent = await client.call_tool("apizr_delivery_run", {})
            assert absent.structured_content["error"]["code"] == "invalid_arguments"
            assert (await result(client, "status")).outcomes[0].state == "not_started"

    anyio.run(exercise)
    assert calls == [] and not Path(batch.evidence_root).exists()


@pytest.mark.parametrize("state", ["complete", "partial", "failed"])
def test_run_and_resume_reuse_coordinator_and_return_business_results(
    project, tmp_path, monkeypatch, state
):
    batch, calcs, app = configured(project, tmp_path)
    managed = Managed()
    if state == "partial":
        managed.fail = (
            "attest",
            batch.destinations[1].push.destination.rsplit(":", 1)[0],
        )

    def invoke(*args, **kwargs):
        assert kwargs["directory"] == Path(calcs.session.delivery.plugins_dir)
        assert kwargs["operator_policy"] == calcs.session.analysis.operator_policy
        if state == "failed":
            raise RuntimeError("must not reach native")
        return managed(*args, **kwargs)

    # All-destination refusal remains an ordinary typed failed BatchResult.
    from apizr.operator_policy import AuthorizationDenied

    def denied(*args, **kwargs):
        raise AuthorizationDenied("operator_repository_denied")

    monkeypatch.setattr(
        operations, "run_extension", denied if state == "failed" else invoke
    )

    async def exercise():
        async with Client(app) as client:
            initial = await result(client, "status")
            assert all(o.state == "not_started" for o in initial.outcomes)
            missing = await client.call_tool("apizr_delivery_resume", arguments(batch))
            assert (
                missing.structured_content["error"]["code"]
                == "delivery_evidence_invalid"
            )
            delivered = await result(client, "run", arguments(batch))
            assert delivered.state == state
            assert await result(client, "status") == delivered
            before = len(managed.calls)
            repeat = await client.call_tool("apizr_delivery_run", arguments(batch))
            assert (
                repeat.structured_content["error"]["code"]
                == "delivery_evidence_invalid"
            )
            assert len(managed.calls) == before
            if state != "failed":
                managed.fail = None
                recovered = await result(client, "resume", arguments(batch))
                assert recovered.state == "complete"
                resumed = managed.calls[before:]
                assert not any(op in {"build", "push"} for op, _, _ in resumed)
                assert sum(op == "attest" for op, _, _ in resumed) == (
                    1 if state == "partial" else 0
                )
                for i in (0, 2):
                    assert recovered.outcomes[i].proof == delivered.outcomes[i].proof
                assert await result(client, "status") == recovered
            raw = delivered.model_dump_json()
            for secret in [
                "/private/",
                str(tmp_path),
                "key_file",
                "trust_store",
                "authentication",
                "plugins_dir",
            ]:
                assert secret not in raw

    anyio.run(exercise)


def test_startup_snapshot_is_used_once_and_recovery_selection_is_preserved(
    project, tmp_path, monkeypatch
):
    from apizr.delivery_batch import BatchRequest

    batch = request(tmp_path)
    data = batch.model_dump(mode="json", by_alias=True)
    data["destinations"][0]["selected_artifact"] = (
        "registry.example/team/service-0@sha256:" + "a" * 64
    )
    data["destinations"][0]["recovery_reference"] = (
        "registry.example/team/service-0@sha256:" + "b" * 64
    )
    batch = BatchRequest.model_validate_json(json.dumps(data))
    session = McpSession(
        analysis=project[1],
        delivery=DeliverySession(request=batch, plugins_dir=str(tmp_path / "plugins")),
    )
    calcs = server.Calculations(session, ServerLimits())
    calls = []

    def deliver(captured, **kwargs):
        calls.append((captured, kwargs))
        assert captured == batch
        assert kwargs["directory"] == Path(session.delivery.plugins_dir)
        assert kwargs["operator_policy"] == session.analysis.operator_policy
        return inspect_batch(captured)

    monkeypatch.setattr(server, "deliver_batch", deliver)

    async def exercise():
        async with Client(server.create_server(calcs)) as client:
            await result(client, "run", arguments(batch))
            await result(client, "resume", arguments(batch))

    anyio.run(exercise)
    assert [kw["resume"] for _, kw in calls] == [False, True]
    assert len(calls) == 2


def test_cancellation_blocks_other_tools_and_waits_for_native_cleanup(
    project, tmp_path, monkeypatch
):
    batch, calcs, app = configured(project, tmp_path)
    started, finished = Event(), Event()
    calls = []

    def controlled(*args, **kwargs):
        calls.append(args)
        started.set()
        assert kwargs["cancel"].wait(5)
        finished.set()
        raise InvocationCancelled()

    monkeypatch.setattr(operations, "run_extension", controlled)

    async def exercise():
        async with Client(app, mode="legacy") as client:
            scope = anyio.CancelScope()

            async def call():
                with scope:
                    await client.call_tool("apizr_delivery_run", arguments(batch))

            async with anyio.create_task_group() as tasks:
                tasks.start_soon(call)
                with anyio.fail_after(5):
                    while not started.is_set():
                        await anyio.sleep(0.01)
                assert len((await client.list_tools()).tools) == 6
                for name in [
                    "apizr_analyze",
                    "apizr_delivery_status",
                    "apizr_delivery_resume",
                ]:
                    reply = await client.call_tool(
                        name, arguments(batch) if name.endswith("resume") else {}
                    )
                    assert reply.structured_content["error"]["code"] == "server_busy"
                scope.cancel()
            with anyio.fail_after(5):
                while calcs.active:
                    await anyio.sleep(0.01)
            assert finished.is_set() and not calcs.fatal.is_set()
            retained = await result(client, "status")
            assert retained.state == "cancelled"
            assert len(calls) == 1
            assert all(o.state == "not_started" for o in retained.outcomes[1:])

    anyio.run(exercise)


@pytest.mark.parametrize("fault", ["cleanup", "exception", "large", "arguments"])
def test_fixed_errors_and_response_bounds(project, tmp_path, monkeypatch, fault):
    batch, calcs, app = configured(
        project,
        tmp_path,
        limits=ServerLimits(max_response_bytes=2048) if fault == "large" else None,
    )
    managed = Managed()

    def invoke(*args, **kwargs):
        if fault == "cleanup":
            raise CleanupFailed()
        if fault == "exception":
            raise RuntimeError("PRIVATE key /secret/path Docker stderr")
        return managed(*args, **kwargs)

    monkeypatch.setattr(operations, "run_extension", invoke)

    async def exercise():
        async with Client(app) as client:
            args = arguments(batch) | (
                {"PRIVATE": "x" * 65536} if fault == "arguments" else {}
            )
            reply = await client.call_tool("apizr_delivery_run", args)
            expected = {
                "cleanup": "cleanup_unconfirmed",
                "exception": "delivery_operation_failed",
                "large": "response_too_large",
                "arguments": "arguments_too_large",
            }[fault]
            assert (
                reply.is_error and reply.structured_content["error"]["code"] == expected
            )
            assert (
                "PRIVATE" not in reply.model_dump_json()
                and "/secret/path" not in reply.model_dump_json()
            )
            if fault == "cleanup":
                assert calcs.fatal.is_set()
                assert (
                    await client.call_tool("apizr_delivery_status", {})
                ).structured_content["error"]["code"] == "cleanup_unconfirmed"

    anyio.run(exercise)
