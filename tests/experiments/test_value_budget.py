"""Finite-value admission counts exact canonical bytes without a JSON copy."""

import json

import pytest
from pydantic import TypeAdapter

from apizr.experiments import values


@pytest.mark.parametrize(
    "value",
    [
        "",
        "ascii",
        'quote"slash\\',
        "é😀",
        "\b\t\n\f\r",
        "\x00\x01\x1f",
        "\u2028\u2029",
        "\x7f\x80",
    ],
)
def test_json_string_accounting_matches_canonical_utf8(value):
    assert values.json_string_size(value) == len(
        json.dumps(value, ensure_ascii=False).encode("utf-8")
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        0,
        -(2**63),
        1e-7,
        1e20,
        -0.0,
        "é\\\n",
        [],
        {},
        [1, None, False, "é"],
        {"é": [1e-7, None], "esc\\": "\x01"},
    ],
)
def test_exact_value_boundary_and_one_byte_over(monkeypatch, value):
    size = len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    adapter = TypeAdapter(values.FiniteValue)
    monkeypatch.setattr(values, "MAX_VALUE_BYTES", size)
    admitted = adapter.validate_python(value)
    assert adapter.dump_python(admitted, mode="json") == value
    monkeypatch.setattr(values, "MAX_VALUE_BYTES", size - 1)
    with pytest.raises(ValueError, match="experiment_value_byte_size"):
        adapter.validate_python(value)
