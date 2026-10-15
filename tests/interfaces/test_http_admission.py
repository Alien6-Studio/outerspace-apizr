"""Cumulative ASGI admission precedes downstream framework/SDK parsing."""

import asyncio
import json

import pytest

from apizr.interfaces.http_admission import JsonAdmission


def exchange(
    chunks, *, limit=16, method="POST", kind="http", headers=(), disconnect=False
):
    received = []
    sent = []
    messages = iter(
        [{"type": "http.disconnect"}]
        if disconnect
        else [
            {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
            for i, chunk in enumerate(chunks)
        ]
    )

    async def receive():
        return next(messages, {"type": "http.disconnect"})

    async def send(message):
        sent.append(message)

    async def decoder(scope, receive, send):
        message = await receive()
        received.append(message)
        received.append(await receive())
        if method == "POST" and kind == "http":
            json.loads(message["body"])

    asyncio.run(
        JsonAdmission(decoder, max_bytes=limit)(
            {"type": kind, "method": method, "headers": headers}, receive, send
        )
    )
    return received, sent


@pytest.mark.parametrize(
    "headers", [[], [(b"content-length", b"1")], [(b"transfer-encoding", b"chunked")]]
)
def test_chunked_byte_limit_rejects_before_decoder(headers):
    received, sent = exchange([b'"1234567', b'8901234567"'], headers=headers)
    assert not received
    assert sent[0]["status"] == 413
    assert len(sent[1]["body"]) < 100


@pytest.mark.parametrize(
    "raw",
    [b"[" * 65 + b"0" + b"]" * 65, b'"\xff"', b"}"],
    ids=["depth", "utf8", "structure"],
)
def test_structure_and_encoding_refused_before_decoder(raw):
    received, sent = exchange([raw], limit=1000)
    assert not received and sent[0]["status"] == 422


def test_exact_limit_replays_original_body_once_then_preserves_disconnect():
    received, sent = exchange([b'"', "éé".encode(), b'"'], limit=6)
    assert received == [
        {"type": "http.request", "body": '"éé"'.encode(), "more_body": False},
        {"type": "http.disconnect"},
    ]
    assert not sent


@pytest.mark.parametrize(
    "method,kind",
    [("GET", "http"), ("DELETE", "http"), ("POST", "lifespan"), ("POST", "websocket")],
)
def test_other_asgi_streams_pass_through(method, kind):
    received, sent = exchange([b"original"], limit=1, method=method, kind=kind)
    assert received[0]["body"] == b"original" and not sent


def test_disconnect_during_admission_never_reaches_decoder():
    assert exchange([], disconnect=True) == ([], [])
