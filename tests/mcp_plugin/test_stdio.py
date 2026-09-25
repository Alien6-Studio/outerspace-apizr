import os

import anyio
import pytest
from apizr_mcp.stdio import Input, Output, StdioRefused


@pytest.mark.parametrize(
    "data,expected", [(b"abc\nxyz\n", ["abc\n", "xyz\n"]), (b"", [])]
)
def test_bounded_lines_and_eof(data, expected):
    read, write = os.pipe()
    os.set_blocking(read, False)
    try:
        os.write(write, data)
        os.close(write)

        async def exercise():
            event = anyio.Event()
            source = Input(read, 16, event)
            assert [line async for line in source] == expected
            assert event.is_set()

        anyio.run(exercise)
    finally:
        os.close(read)


@pytest.mark.parametrize(
    "data,code",
    [
        (b"xxxxxxxx", "request_too_large"),
        (b"incom", "incomplete_request"),
        (b"\xff\n", "invalid_utf8"),
    ],
)
def test_invalid_or_oversized_frames(data, code):
    read, write = os.pipe()
    try:
        os.write(write, data)
        os.close(write)

        async def exercise():
            source = Input(read, 8, anyio.Event())
            with pytest.raises(StdioRefused, match=code):
                await source.__anext__()

        anyio.run(exercise)
    finally:
        os.close(read)


def test_output_limit_and_flush():
    read, write = os.pipe()
    os.set_blocking(write, False)
    try:

        async def exercise():
            sink = Output(write, 16)
            await sink.write("result\n")
            await sink.flush()
            with pytest.raises(StdioRefused):
                await sink.write("x" * 17)

        anyio.run(exercise)
        assert os.read(read, 1024) == b"result\n"
    finally:
        os.close(read)
        os.close(write)


def test_claimed_stdio_keeps_unintended_output_off_protocol():
    from apizr_mcp.stdio import streams

    saved_in, saved_out = os.dup(0), os.dup(1)
    incoming, produce = os.pipe()
    consume, outgoing = os.pipe()
    try:
        os.write(produce, b"request\n")
        os.close(produce)
        os.dup2(incoming, 0)
        os.dup2(outgoing, 1)

        async def exercise():
            with streams(1024, 1024, anyio.Event()) as (read, write):
                assert await read.__anext__() == "request\n"
                assert os.read(0, 1) == b""
                await write.write("response\n")

        anyio.run(exercise)
        assert os.read(consume, 1024) == b"response\n"
    finally:
        os.dup2(saved_in, 0)
        os.dup2(saved_out, 1)
        for fd in (saved_in, saved_out, incoming, consume, outgoing):
            os.close(fd)
