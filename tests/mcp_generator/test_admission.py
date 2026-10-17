"""Raw-line limits and native descriptor ownership around public SDK injection."""

import io
import threading
from contextlib import nullcontext
from types import SimpleNamespace

import anyio
import pytest

from apizr.generators.mcp import transport
from apizr.interfaces.json_budget import MAX_JSON_BYTES


@pytest.mark.parametrize(
    "raw", [b"[" * 65 + b"0" + b"]" * 65 + b"\n", b'"\xff"\n'], ids=["depth", "utf8"]
)
def test_structural_refusal_is_small_and_next_frame_survives(raw):
    reader = transport.BoundedInput(io.BytesIO(raw + b"{}\n"))
    assert reader.readline() == "{\n"
    assert reader.readline() == "{}\n"
    assert reader.readline() == ""


def test_binary_byte_limit_precedes_decoding_and_ends_oversized_stream():
    stream = io.BytesIO('"ééé"\n{}\n'.encode())
    reader = transport.BoundedInput(stream, max_bytes=6)
    assert reader.readline() == "{\n"
    consumed = stream.tell()
    assert consumed == 7
    assert reader.readline() == "" and stream.tell() == consumed


def test_production_line_read_is_bounded_without_allocating_large_input():
    class Probe(io.BytesIO):
        def readline(self, size=-1):
            assert size == MAX_JSON_BYTES + 1
            return b"{}\n"

    assert transport.BoundedInput(Probe()).readline() == "{}\n"


@pytest.fixture
def descriptors(monkeypatch):
    calls = []
    monkeypatch.setattr(transport, "os", SimpleNamespace(**vars(transport.os)))
    wire = io.BytesIO(b"{}\n")
    monkeypatch.setattr(transport, "_INPUT_LOCK", threading.Lock())
    monkeypatch.setattr(transport.os, "dup", lambda fd: 9)
    monkeypatch.setattr(transport.os, "open", lambda *args: 10)
    monkeypatch.setattr(
        transport.os, "dup2", lambda source, target: calls.append((source, target))
    )
    monkeypatch.setattr(transport.os, "close", lambda fd: calls.append(("close", fd)))
    monkeypatch.setattr(transport.os, "fdopen", lambda *args, **kwargs: wire)
    monkeypatch.setattr(transport, "rebind_stdin", lambda: calls.append("rebind"))
    return calls, wire


@pytest.mark.parametrize("failure", [False, True])
def test_claim_diverts_then_restores_and_closes_only_owned_stream(descriptors, failure):
    calls, wire = descriptors
    with pytest.raises(ValueError) if failure else nullcontext():
        with transport.claimed_input() as reader:
            assert reader.readline() == "{}\n"
            with pytest.raises(RuntimeError, match="already claimed"):
                with transport.claimed_input():
                    pytest.fail("concurrent claim")
            assert calls[:3] == [(10, 0), "rebind", ("close", 10)]
            assert not wire.closed
            if failure:
                raise ValueError("body failed")
    assert calls[-3:] == [(9, 0), "rebind", ("close", 9)]
    assert wire.closed and not transport._INPUT_LOCK.locked()


@pytest.mark.parametrize(
    "fault", ["dup", "duplicate", "open", "divert", "fdopen", "restore"]
)
def test_claim_failure_does_not_recycle_active_wire(descriptors, monkeypatch, fault):
    calls, wire = descriptors

    def fail(*args, **kwargs):
        raise OSError("test-owned failure")

    if fault == "dup":
        monkeypatch.setattr(transport.os, "dup", fail)
    elif fault == "duplicate":
        monkeypatch.setattr(transport.os, "dup", lambda fd: 1)
    elif fault in {"open", "fdopen"}:
        monkeypatch.setattr(transport.os, fault, fail)
    else:

        def dup2(source, target):
            calls.append((source, target))
            if source == (10 if fault == "divert" else 9):
                fail()

        monkeypatch.setattr(transport.os, "dup2", dup2)
    with pytest.raises((OSError, RuntimeError)):
        with transport.claimed_input():
            pass
    assert transport._INPUT_LOCK.locked() is (fault == "restore")
    if fault == "restore":
        assert not wire.closed and ("close", 9) not in calls
    if fault in {"divert", "fdopen"}:
        assert (9, 0) in calls


def test_windows_handle_rebound_through_sdk_utility(monkeypatch):
    calls = []
    monkeypatch.setattr(transport, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr("mcp.os.win32.utilities.rebind_std_handle_to_fd", calls.append)
    transport.rebind_stdin()
    assert calls == [0]


def test_stdio_passes_bounded_input_through_public_sdk_argument(
    descriptors, monkeypatch
):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def sdk(*, stdin):
        assert await stdin.readline() == "{}\n"
        yield ("read", "write")

    monkeypatch.setattr(transport, "sdk_stdio_server", sdk)

    async def exercise():
        async with transport.stdio_server() as streams:
            assert streams == ("read", "write")

    anyio.run(exercise)


def test_mcp_dual_representation_is_admitted_before_sdk_models(monkeypatch):
    monkeypatch.setattr(transport, "MAX_JSON_BYTES", 1200)
    assert transport.tool_result({"small": True}).structured_content == {"small": True}
    with pytest.raises(ValueError, match="json_byte_limit"):
        transport.tool_result({"x": "a" * 100})


def test_posix_rebind_does_not_invoke_windows_utility(monkeypatch):
    monkeypatch.setattr(transport, "sys", SimpleNamespace(platform="darwin"))

    def forbidden(*args):
        raise AssertionError("Windows handle API reached on POSIX")

    monkeypatch.setattr("mcp.os.win32.utilities.rebind_std_handle_to_fd", forbidden)
    transport.rebind_stdin()


def test_caller_smaller_http_limit_is_preserved():
    from starlette.testclient import TestClient

    app = transport.BoundedServer("admission probe").streamable_http_app(
        max_request_body_size=8
    )
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        response = client.post("/mcp", content=b'"12345678"')
        assert response.status_code == 413
