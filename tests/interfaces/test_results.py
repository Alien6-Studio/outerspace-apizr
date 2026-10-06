"""Python result normalization is separate from the strict JSON input contract."""

import json
from dataclasses import dataclass

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel

from apizr.execution.protocol import finite_json
from apizr.interfaces.results import finite_json_value, normalize_result_for_json


@pytest.mark.parametrize(
    "value,expected",
    [
        ((), []),
        ((1, 2), [1, 2]),
        (([12, 15, 15], [8, 8, 9]), [[12, 15, 15], [8, 8, 9]]),
        ({"support": ("61.8%", 10.674)}, {"support": ["61.8%", 10.674]}),
        ([(1, 2)], [[1, 2]]),
        ({"ok": (1, 2)}, {"ok": [1, 2]}),
        (([1, 2], (3, 4)), [[1, 2], [3, 4]]),
        (
            {"a": [(None, {"b": ([True, False], (1, 2.5, "s"))})]},
            {"a": [[None, {"b": [[True, False], [1, 2.5, "s"]]}]]},
        ),
        (None, None),
        (True, True),
        (False, False),
        (42, 42),
        (2.5, 2.5),
        ("s", "s"),
    ],
)
def test_result_normalization(value, expected):
    original = repr(value)
    normalized = normalize_result_for_json(value)
    assert normalized == expected
    assert repr(value) == original
    assert finite_json(normalized) == normalized
    assert json.loads(json.dumps(normalized, allow_nan=False)) == normalized
    if isinstance(value, bool):
        assert normalized is value


@dataclass
class Record:
    value: int = 1


class Model(BaseModel):
    value: int = 1


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        object(),
        complex(1, 2),
        {1: (1, 2)},
        {1, 2},
        frozenset({1}),
        Record(),
        Model(),
        iter([1, 2]),
    ],
)
@pytest.mark.parametrize("nested", [False, True])
def test_unsupported_results_never_coerced(value, nested):
    with pytest.raises(ValueError, match="Result is not a finite JSON value"):
        normalize_result_for_json({"nested": [(value,)]} if nested else value)


@pytest.mark.parametrize("tuple_cycle", [False, True])
def test_recursive_result_keeps_controlled_recursion_failure(tuple_cycle):
    value = []
    value.append((value,) if tuple_cycle else value)
    with pytest.raises(RecursionError):
        normalize_result_for_json(value)


def test_containers_are_copied_without_mutation_or_boolean_coercion():
    inner = [True, 1, None]
    original = {"nested": (inner,)}
    result = normalize_result_for_json(original)
    assert result == {"nested": [[True, 1, None]]}
    assert result is not original and result["nested"][0] is not inner
    assert result["nested"][0][0] is True
    result["nested"][0].append(2)
    assert inner == [True, 1, None]


@pytest.mark.parametrize("value", [(1, 2), [(1, 2)], {"nested": (1, 2)}])
def test_input_json_and_worker_protocol_still_reject_python_tuples(value):
    with pytest.raises(ValueError):
        finite_json_value(value)
    with pytest.raises(ValueError):
        finite_json(value)


SCALARS = (
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text()
)
RESULTS = st.recursive(
    SCALARS,
    lambda children: (
        st.lists(children, max_size=5)
        | st.lists(children, max_size=5).map(tuple)
        | st.dictionaries(st.text(), children, max_size=5)
    ),
    max_leaves=30,
)


@given(RESULTS)
def test_supported_results_lower_to_finite_json_and_round_trip(value):
    normalized = normalize_result_for_json(value)
    assert finite_json(normalized) == normalized
    assert json.loads(json.dumps(normalized, allow_nan=False)) == normalized
    assert normalize_result_for_json(normalized) == normalized
