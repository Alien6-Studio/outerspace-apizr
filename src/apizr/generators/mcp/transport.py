"""MCP wire admission through public SDK streams and ASGI composition."""

import os
import sys
import threading
from collections.abc import Generator
from contextlib import asynccontextmanager, contextmanager
from io import TextIOBase
from typing import IO, Any, BinaryIO, cast

import anyio
from mcp.server import Server
from mcp.server.stdio import stdio_server as sdk_stdio_server
from mcp.types import CallToolResult, TextContent
from starlette.applications import Starlette

from apizr.interfaces.http_admission import JsonAdmission
from apizr.interfaces.json_budget import (
    MAX_JSON_BYTES,
    JsonBudget,
    bounded_dumps,
    preflight,
)

_INPUT_LOCK = threading.Lock()


class BoundedServer(Server[dict[str, object]]):
    """Keep public SDK HTTP configuration while admitting before SDK parsing."""

    def streamable_http_app(self, **kwargs: Any) -> Starlette:
        app = super().streamable_http_app(**kwargs)
        # Retain the pinned SDK's 4 MiB default and any stricter caller limit.
        limit = min(
            kwargs.get("max_request_body_size", 4 * 1024 * 1024), MAX_JSON_BYTES
        )
        app.add_middleware(JsonAdmission, max_bytes=limit)
        return app


class BoundedInput(TextIOBase):
    """Read a bounded binary frame before UTF-8 decoding or SDK validation.

    Structural failures become a small parse error and permit the next frame.
    An overlong frame terminates this input stream without draining an unbounded
    line. The caller owns the underlying binary stream.
    """

    def __init__(self, stream: BinaryIO, *, max_bytes: int = MAX_JSON_BYTES) -> None:
        self.stream = stream
        self.max_bytes = max_bytes
        self.failed = False

    def readline(self, size: int = -1, /) -> str:
        if self.failed:
            return ""
        raw = self.stream.readline(self.max_bytes + 1)
        if len(raw) > self.max_bytes:
            self.failed = True
            return "{\n"
        if not raw:
            return ""
        try:
            return preflight(raw, max_bytes=self.max_bytes)
        except (ValueError, UnicodeError):
            return "{\n"


def rebind_stdin() -> None:
    if sys.platform == "win32":
        from mcp.os.win32.utilities import rebind_std_handle_to_fd

        rebind_std_handle_to_fd(0)


@contextmanager
def claimed_input() -> Generator[BoundedInput]:
    """Divert native business-code reads to EOF while serving a private wire fd.

    Fail closed if diversion cannot be established. The duplicate is closed only
    after the SDK task group has joined its non-abandoning file reader. A failed
    restoration retains the descriptor and claim rather than recycling either.
    SDK-owned stdout keeps its existing independent claim and diversion.
    """
    if not _INPUT_LOCK.acquire(blocking=False):
        raise RuntimeError("MCP stdin already claimed")
    duplicate: int | None = None
    stream: BinaryIO | None = None
    diverted = False
    restored = False
    try:
        duplicate = os.dup(0)
        if duplicate <= 2:
            raise RuntimeError("MCP stdin duplicate overlaps standard descriptors")
        diversion = os.open(os.devnull, os.O_RDONLY)
        try:
            diverted = True
            os.dup2(diversion, 0)
            rebind_stdin()
        finally:
            os.close(diversion)
        stream = os.fdopen(duplicate, "rb", closefd=False)
        yield BoundedInput(stream)
    finally:
        try:
            if diverted:
                assert duplicate is not None
                os.dup2(duplicate, 0)
                rebind_stdin()
            restored = True
        finally:
            if restored:
                if stream is not None:
                    stream.close()
                if duplicate is not None:
                    os.close(duplicate)
                _INPUT_LOCK.release()


@asynccontextmanager
async def stdio_server():
    with claimed_input() as reader:
        async with sdk_stdio_server(
            stdin=anyio.wrap_file(cast(IO[str], reader))
        ) as streams:
            yield streams


def tool_result(value: object) -> CallToolResult:
    """Admit both MCP result representations before SDK model construction."""
    admitted = JsonBudget().visit(value)
    value = admitted if isinstance(admitted, dict) else {"result": admitted}
    text = bounded_dumps(value)
    JsonBudget(max_bytes=MAX_JSON_BYTES - 1024).visit(
        {
            "content": [{"type": "text", "text": text}],
            "structuredContent": value,
            "isError": False,
        }
    )
    return CallToolResult(
        content=[TextContent(type="text", text=text)], structured_content=value
    )
