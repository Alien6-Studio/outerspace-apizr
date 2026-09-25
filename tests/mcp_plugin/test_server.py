import json
from threading import Event
from types import SimpleNamespace

import anyio
import pytest
from apizr_mcp import server
from apizr_mcp.model import Job, ServerLimits
from apizr_mcp.worker import calculate
from mcp import Client

from apizr.extension_runtime import (
    CleanupFailed,
    InvocationCancelled,
    InvocationTimeout,
)


def setup(project, monkeypatch, limits=None, invoke=None):
    _, scope = project

    def normal(python, module, operation, arguments, **kwargs):
        assert kwargs["environment"] == {}
        assert module == "apizr_mcp" and operation == "calculate"
        return SimpleNamespace(
            result=calculate(Job.model_validate_json(json.dumps(arguments)))
        )

    monkeypatch.setattr(server, "invoke_extension", invoke or normal)
    calculations = server.Calculations(scope, limits or ServerLimits())
    return calculations, server.create_server(calculations)


def test_sdk_tools_validation_errors_and_business_results(project, monkeypatch):
    calculations, app = setup(project, monkeypatch)

    async def exercise():
        async with Client(app) as client:
            tools = (await client.list_tools()).tools
            assert len(tools) == 3
            assert all(
                t.annotations.read_only_hint and t.annotations.destructive_hint is False
                for t in tools
            )
            for name in ["apizr_analyze", "apizr_readiness", "apizr_plan_exposure"]:
                result = await client.call_tool(name, {})
                assert not result.is_error
                assert "repository_digest" in result.structured_content
            invalid = await client.call_tool("apizr_analyze", {"root": "/"})
            assert (
                invalid.is_error
                and invalid.structured_content["error"]["code"] == "invalid_arguments"
            )
            unknown = await client.call_tool("not_a_tool", {})
            assert unknown.is_error
            too_large = await client.call_tool("apizr_analyze", {"x": "a" * 65536})
            assert (
                too_large.structured_content["error"]["code"] == "arguments_too_large"
            )
            stale = await client.call_tool(
                "apizr_analyze", {"expected_repository_digest": "a" * 64}
            )
            assert stale.structured_content["error"]["code"] == "repository_changed"

    anyio.run(exercise)
    assert not calculations.active


@pytest.mark.parametrize(
    "error,code",
    [
        (InvocationTimeout(), "timeout"),
        (CleanupFailed(), "cleanup_failed"),
        (ValueError(), "operation_failed"),
    ],
)
def test_worker_errors_are_redacted_and_following_call_works(
    project, monkeypatch, error, code
):
    state = [True]

    def invoke(*args, **kwargs):
        if state.pop() if state else False:
            raise error
        return SimpleNamespace(
            result=calculate(Job.model_validate_json(json.dumps(args[3])))
        )

    calcs, app = setup(project, monkeypatch, invoke=invoke)

    async def exercise():
        async with Client(app) as client:
            result = await client.call_tool("apizr_analyze", {})
            assert (
                result.is_error and result.structured_content["error"]["code"] == code
            )
            next_result = await client.call_tool("apizr_analyze", {})
            if code == "cleanup_failed":
                assert (
                    next_result.structured_content["error"]["code"]
                    == "cleanup_unconfirmed"
                )
            else:
                assert not next_result.is_error

    anyio.run(exercise)
    assert not calcs.active


def test_cancellation_waits_for_cleanup_and_admission_is_bounded(project, monkeypatch):
    started, finished = Event(), Event()
    first = [True]

    def invoke(*args, **kwargs):
        if first:
            first.pop()
            started.set()
            assert kwargs["cancel"].wait(5)
            finished.set()
            raise InvocationCancelled()
        return SimpleNamespace(
            result=calculate(Job.model_validate_json(json.dumps(args[3])))
        )

    calcs, app = setup(project, monkeypatch, invoke=invoke)

    async def exercise():
        async with Client(app, mode="legacy") as client:
            cancellation = anyio.CancelScope()

            async def call():
                with cancellation:
                    await client.call_tool("apizr_analyze", {})

            async with anyio.create_task_group() as tg:
                tg.start_soon(call)
                with anyio.fail_after(5):
                    while not started.is_set():
                        await anyio.sleep(0.01)
                assert (
                    await client.call_tool("apizr_readiness", {})
                ).structured_content["error"]["code"] == "server_busy"
                await client.send_ping()
                cancellation.cancel()
            with anyio.fail_after(5):
                while calcs.active:
                    await anyio.sleep(0.01)
            assert finished.is_set()
            assert not (await client.call_tool("apizr_analyze", {})).is_error

    anyio.run(exercise)


def test_large_response_and_bad_worker_result(project, monkeypatch):
    _, app = setup(project, monkeypatch, ServerLimits(max_response_bytes=2048))

    async def exercise():
        async with Client(app) as client:
            result = await client.call_tool("apizr_analyze", {})
            assert (
                result.is_error
                and result.structured_content["error"]["code"] == "response_too_large"
            )

    anyio.run(exercise)
    _, app = setup(
        project, monkeypatch, invoke=lambda *a, **k: SimpleNamespace(result=[])
    )
    anyio.run(exercise_bad, app)


async def exercise_bad(app):
    async with Client(app) as client:
        assert (await client.call_tool("apizr_analyze", {})).structured_content[
            "error"
        ]["code"] == "operation_failed"


def test_redacted_exception_groups():
    from apizr_mcp.stdio import StdioRefused

    assert (
        server.diagnostic(
            ExceptionGroup(
                "secret",
                [ValueError("private/path"), StdioRefused("request_too_large")],
            )
        )
        == "request_too_large"
    )
    assert server.diagnostic(ValueError("secret")) == "startup_or_transport_refused"


def test_serve_lifecycle_with_official_session(project, monkeypatch):
    from contextlib import asynccontextmanager, contextmanager

    from mcp import ClientSession

    path, _ = project
    setup(project, monkeypatch)

    async def exercise():
        to_server, read_server = anyio.create_memory_object_stream(0)
        to_client, read_client = anyio.create_memory_object_stream(0)
        end = []

        @contextmanager
        def streams(*args):
            end.append(args[2])
            yield None, None

        @asynccontextmanager
        async def stdio_server(**kwargs):
            yield read_server, to_client

        monkeypatch.setattr(server, "streams", streams)
        monkeypatch.setattr(server, "stdio_server", stdio_server)
        with anyio.fail_after(10):
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(server.serve, path, ServerLimits())
                async with ClientSession(read_client, to_server) as client:
                    await client.initialize()
                    assert len((await client.list_tools()).tools) == 3
                    assert not (await client.call_tool("apizr_readiness", {})).is_error
                end[0].set()

    anyio.run(exercise)


def test_server_entrypoint_validation_and_interrupt(project, monkeypatch, capsys):
    path, _ = project
    assert server.main(["--project", "relative"]) == 2
    assert server.main(["--project", str(path), "--timeout-ms", "0"]) == 2

    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(server.anyio, "run", interrupt)
    assert server.main(["--project", str(path)]) == 130
    assert capsys.readouterr().out == ""
