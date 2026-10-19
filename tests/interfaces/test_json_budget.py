"""Adversarial admission before recursive copies, decoders and encoder chunks."""

import json

import pytest

from apizr.execution import protocol
from apizr.interfaces.json_budget import (
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    JsonBudget,
    bounded_dumps,
    preflight,
)
from apizr.interfaces.results import normalize_rest_result


def nested(depth):
    value = 0
    for _ in range(depth):
        value = [value]
    return value


@pytest.mark.parametrize(
    "value", [None, True, 42, -1.25, 'é😀\n\x00\\"', [], {}, {"x": [1, 2]}]
)
def test_exact_compact_utf8_budget(value):
    expected = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    size = len(expected.encode())
    assert bounded_dumps(value, max_bytes=size) == expected
    with pytest.raises(ValueError, match="json_byte_limit"):
        bounded_dumps(value, max_bytes=size - 1)


@pytest.mark.parametrize("dictionary", [False, True])
def test_broad_containers_refused_without_iteration(dictionary):
    class NoWalkList(list):
        def __iter__(self):
            raise AssertionError("must refuse from length before traversal or copy")

    class NoWalkDict(dict):
        def items(self):
            raise AssertionError("must refuse from length before traversal or copy")

    value = (
        NoWalkDict.fromkeys(range(MAX_JSON_NODES), 0)
        if dictionary
        else NoWalkList([0] * MAX_JSON_NODES)
    )
    with pytest.raises(ValueError, match="json_node_limit"):
        JsonBudget().visit(value, copy=True)


def test_node_keys_and_repeated_shared_values_are_charged():
    shared = [0]
    assert JsonBudget(max_nodes=5).visit([shared, shared], copy=True) == [[0], [0]]
    with pytest.raises(ValueError, match="json_node_limit"):
        JsonBudget(max_nodes=4).visit([shared, shared], copy=True)
    with pytest.raises(ValueError, match="json_node_limit"):
        JsonBudget(max_nodes=3).visit([[0], 0], copy=True)
    assert JsonBudget(max_nodes=3).visit({"key": 0}) == {"key": 0}
    with pytest.raises(ValueError, match="json_node_limit"):
        JsonBudget(max_nodes=2).visit({"key": 0})


def test_depth_boundary_matches_raw_admission_and_precedes_decoder(monkeypatch):
    assert JsonBudget().visit(nested(MAX_JSON_DEPTH), copy=True) == nested(
        MAX_JSON_DEPTH
    )
    raw = b"[" * MAX_JSON_DEPTH + b"0" + b"]" * MAX_JSON_DEPTH
    assert preflight(raw) == raw.decode()
    raw = b"[" + raw + b"]"
    monkeypatch.setattr(
        protocol.json, "loads", lambda *a, **k: pytest.fail("decoder reached")
    )
    with pytest.raises(ValueError, match="json_structure_limit"):
        protocol.decode(protocol.frame(raw), len(raw))
    with pytest.raises(ValueError, match="json_depth_limit"):
        JsonBudget().visit(nested(MAX_JSON_DEPTH + 1), copy=True)


def test_string_escape_amplification_is_counted_in_small_chunks(monkeypatch):
    original = json.dumps
    sizes = []

    def observed(value, **kwargs):
        if isinstance(value, str):
            sizes.append(len(value))
            assert len(value) <= 4096
        return original(value, **kwargs)

    monkeypatch.setattr(json, "dumps", observed)
    with pytest.raises(ValueError, match="json_byte_limit"):
        bounded_dumps("\x00" * 9000, max_bytes=10000)
    assert sizes


def test_worker_checks_size_before_pydantic_copy(monkeypatch):
    monkeypatch.setattr(
        protocol.JSON_VALUE,
        "validate_python",
        lambda *a, **k: pytest.fail("copy reached"),
    )
    with pytest.raises(protocol.SizeExceeded, match="frame_size"):
        protocol.encode("\x00" * 100, 200)


def test_large_integer_refused_before_decimal_conversion():
    with pytest.raises(ValueError, match="json_byte_limit"):
        JsonBudget(max_bytes=2).visit(1 << 100000)


def test_rest_preserves_container_lowering_without_mutating_source():
    value = {"x": ({1, 2}, frozenset({3}))}
    result = normalize_rest_result(value)
    assert sorted(result["x"][0]) == [1, 2]
    assert result["x"][1] == [3]
    assert isinstance(value["x"][0], set)
