import io
import struct

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apizr.execution.protocol import (
    ProtocolError,
    SizeExceeded,
    decode,
    encode,
    finite_json,
    frame,
    read_frame,
)
from apizr.generators.mcp.runtime import result_value

JSON = st.recursive(
    st.none() | st.booleans() | st.integers(-10000, 10000) | st.text(max_size=15),
    lambda children: (
        st.lists(children, max_size=5)
        | st.dictionaries(st.text(max_size=10), children, max_size=5)
    ),
    max_leaves=10,
)


@given(JSON)
def test_frame_round_trip_matches_mcp_result_semantics(value):
    payload = encode(value, 100000)
    assert decode(frame(payload), 100000) == value == result_value(value)
    assert read_frame(io.BytesIO(frame(payload)), 100000) == value
    assert encode(value, len(payload)) == payload
    with pytest.raises(SizeExceeded):
        encode(value, len(payload) - 1)


@pytest.mark.parametrize(
    "value", [(1,), {1}, b"a", object(), {1: "a"}, float("nan"), float("inf")]
)
def test_non_json_values_rejected_like_mcp(value):
    with pytest.raises(ValueError):
        finite_json(value)
    with pytest.raises(ValueError):
        result_value(value)


@pytest.mark.parametrize(
    "wire",
    [
        b"",
        b"123",
        struct.pack("!Q", 10) + b"{}",
        frame(b"{}") + b"extra",
        frame(b"not json"),
    ],
)
def test_bad_frames_rejected(wire):
    with pytest.raises(ValueError):
        decode(wire, 100)
    with pytest.raises(ValueError):
        read_frame(io.BytesIO(wire), 100)


def test_size_header_checked_before_payload_read():
    with pytest.raises(SizeExceeded):
        read_frame(io.BytesIO(struct.pack("!Q", 10000000)), 100)
    with pytest.raises(ProtocolError):
        read_frame(io.BytesIO(frame(b"{}") + b"x"), 100)
