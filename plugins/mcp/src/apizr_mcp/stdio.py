"""Bounded POSIX byte streams for the SDK's stdio transport, not JSON-RPC."""

import os
from contextlib import contextmanager

import anyio


class StdioRefused(ValueError):
    pass


class Input:
    def __init__(self, descriptor: int, maximum: int, disconnected: anyio.Event):
        self.descriptor = descriptor
        self.maximum = maximum
        self.disconnected = disconnected
        self.pending = bytearray()

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        while True:
            newline = self.pending.find(b"\n")
            if newline >= 0:
                line = bytes(self.pending[: newline + 1])
                del self.pending[: newline + 1]
                if len(line) > self.maximum:
                    raise StdioRefused("request_too_large")
                try:
                    return line.decode("utf-8")
                except UnicodeError:
                    raise StdioRefused("invalid_utf8") from None
            if len(self.pending) >= self.maximum:
                raise StdioRefused("request_too_large")
            await anyio.wait_readable(self.descriptor)
            try:
                data = os.read(
                    self.descriptor, min(4096, self.maximum - len(self.pending))
                )
            except BlockingIOError:
                continue
            if not data:
                self.disconnected.set()
                if self.pending:
                    raise StdioRefused("incomplete_request")
                raise StopAsyncIteration
            self.pending.extend(data)


class Output:
    def __init__(self, descriptor: int, maximum: int):
        self.descriptor = descriptor
        self.maximum = maximum

    async def write(self, text: str) -> None:
        data = text.encode("utf-8")
        if len(data) > self.maximum:
            raise StdioRefused("protocol_response_too_large")
        with anyio.fail_after(5):
            while data:
                await anyio.wait_writable(self.descriptor)
                try:
                    sent = os.write(self.descriptor, data[:65536])
                except BlockingIOError:
                    continue
                data = data[sent:]

    async def flush(self) -> None:
        pass


@contextmanager
def streams(request_limit: int, response_limit: int, disconnected: anyio.Event):
    reader, writer = os.dup(0), os.dup(1)
    try:
        os.set_blocking(reader, False)
        os.set_blocking(writer, False)
        with open(os.devnull, "rb") as empty:
            os.dup2(empty.fileno(), 0)
        # Unintended Python/native writes cannot enter the client's protocol pipe.
        os.dup2(2, 1)
        yield (
            Input(reader, request_limit, disconnected),
            Output(writer, response_limit + 262144),
        )
    finally:
        os.close(reader)
        os.close(writer)
