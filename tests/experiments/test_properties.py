"""Bounded generated values exercise canonical and keyed-data invariants."""

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from apizr.experiments import (
    EvidenceOrigin,
    ExecutionIntent,
    ExperimentPlan,
    Parameter,
    SourceIdentity,
    plan_bytes,
    plan_digest,
)

text = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=20)
scalar = (
    st.none()
    | st.booleans()
    | st.integers(min_value=-(2**63), max_value=2**63 - 1)
    | st.floats(allow_nan=False, allow_infinity=False)
    | text
)
values = st.recursive(
    scalar,
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(text, children, max_size=4)
    ),
    max_leaves=12,
)


def make(parameters):
    return ExperimentPlan(
        subject=SourceIdentity(kind="python", reference="train.py", digest="a" * 64),
        execution=ExecutionIntent(kind="training"),
        parameters=parameters,
    )


@given(values)
@settings(max_examples=60, deadline=None)
def test_finite_json_roundtrip(value):
    plan = make((Parameter(name="x", value=value, origin=EvidenceOrigin.DECLARED),))
    raw = plan_bytes(plan)
    assert plan_bytes(ExperimentPlan.model_validate_json(raw)) == raw
    assert json.loads(raw)["parameters"][0]["value"] == value


@given(
    st.lists(st.integers(min_value=-100000, max_value=100000), min_size=1, max_size=10)
)
@settings(max_examples=40, deadline=None)
def test_order_duplicate_and_semantic_mutation(values):
    records = tuple(
        Parameter(name=f"p{i}", value=value, origin=EvidenceOrigin.DECLARED)
        for i, value in enumerate(values)
    )
    original = make(records)
    assert plan_bytes(make(records[::-1])) == plan_bytes(original)
    with pytest.raises(ValidationError, match="duplicate_identity"):
        make((*records, records[0]))
    changed = Parameter(
        name=records[0].name, value=values[0] + 1, origin=EvidenceOrigin.DECLARED
    )
    assert plan_digest(make((changed, *records[1:]))) != plan_digest(original)
