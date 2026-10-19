"""ASGI JSON admission before framework or MCP SDK decoding."""

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from apizr.interfaces.json_budget import MAX_JSON_BYTES, preflight

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class JsonAdmission:
    """Bound cumulative chunks and JSON structure, then replay one admitted body.

    Content-Length is not trusted. Lifespan, GET/SSE and DELETE retain their
    original streams. A refused request never reaches the downstream decoder.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int = MAX_JSON_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        body = bytearray()
        status = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk: bytes = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                status = 413
                break
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        if not status:
            try:
                preflight(bytes(body), max_bytes=self.max_bytes)
            except (ValueError, UnicodeError):
                status = 422
        if status:
            response = b'{"detail":"JSON admission limit or encoding rejected"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(response)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": response})
            return
        admitted = bytes(body)
        del body
        consumed = False

        async def replay() -> Message:
            nonlocal consumed
            if consumed:
                return await receive()
            consumed = True
            return {"type": "http.request", "body": admitted, "more_body": False}

        await self.app(scope, replay, send)
