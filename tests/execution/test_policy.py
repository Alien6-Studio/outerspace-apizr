import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.capabilities.model import Digest
from apizr.execution import (
    ExecutionPolicy,
    PolicyRefused,
    plan,
    plan_bytes,
    plan_digest,
    policy_bytes,
    policy_digest,
)
from apizr.execution.planner import validate_plan
from apizr.execution.policy import BackendCapabilities, check_controls
from apizr.inspection import inspect_source

from .helpers import planned


@pytest.mark.parametrize(
    "changes",
    [
        {"network": {"mode": "deny"}},
        {"filesystem": {"mode": "sandbox"}},
        {"subprocess": {"mode": "deny"}},
        {"effects": {"require_known": ["network"]}},
        {"effects": {"require_known": ["filesystem_write"]}},
    ],
)
def test_unsupported_security_or_unknown_effect_policy_refuses_before_start(changes):
    with pytest.raises(PolicyRefused):
        planned("def f(): pass", **changes)


def test_backend_capability_availability_and_required_support():
    policy = ExecutionPolicy()
    for backend in [
        BackendCapabilities(available=False),
        BackendCapabilities(available=True, enforced=()),
    ]:
        with pytest.raises(PolicyRefused):
            check_controls(policy, backend)
    check_controls(policy, BackendCapabilities(available=True))


@pytest.mark.parametrize(
    "changes",
    [
        {"limits": {"wall_time_ms": 0}},
        {"limits": {"max_input_bytes": True}},
        {"limits": {"max_output_bytes": 127}},
        {"environment": {"allow": ["BAD=VALUE"]}},
        {"environment": {"inherit": True, "allow": ["LANG"]}},
        {"network": {"mode": "best_effort"}},
        {"secret": "do not store"},
        {"effects": {"require_known": ["invented"]}},
    ],
)
def test_invalid_policies_are_not_silently_downgraded(changes):
    with pytest.raises(ValueError):
        ExecutionPolicy.model_validate(changes)


@settings(max_examples=20, deadline=None)
@given(
    st.integers(1, 10000),
    st.lists(st.sampled_from(["LANG", "TZ", "APIZR_SAMPLE"]), max_size=5),
)
def test_policy_and_plan_canonicalization(timeout, names):
    first = ExecutionPolicy.model_validate(
        {"limits": {"wall_time_ms": timeout}, "environment": {"allow": names}}
    )
    second = ExecutionPolicy.model_validate(
        {
            "environment": {"allow": list(reversed(names))},
            "limits": {"wall_time_ms": timeout},
        }
    )
    assert policy_bytes(first) == policy_bytes(second)
    assert policy_digest(first) == Digest.of_bytes(policy_bytes(first))
    source = b"def f(x: int=2): return x"
    inspection = inspect_source(source, module_name="stable.module")
    a = plan(inspection, source, "f", first)
    b = plan(inspection, source, "python:stable.module:f", second)
    assert plan_bytes(a) == plan_bytes(b)
    assert plan_digest(a) == Digest.of_bytes(plan_bytes(a))
    assert json.loads(plan_bytes(a))["backend_version"] == "apizr.local-process/v1"
    assert validate_plan(a, source, source) == a


@pytest.mark.parametrize(
    "field",
    [
        "policy_digest",
        "ir_digest",
        "readiness_digest",
        "interface_digest",
        "executable_digest",
    ],
)
def test_plan_digests_cannot_be_supplied_independently(field):
    runtime, source = planned("def f(): return 1")
    bad = runtime.model_copy(update={field: Digest.of_bytes(b"other")})
    with pytest.raises(ValueError):
        validate_plan(bad, source, source)


def test_noneligible_and_unknown_selection_remain_errors():
    for source, capability in [
        (b"def f(): yield 1", "f"),
        (b"async def f(): yield 1", "f"),
        (b"def f(): pass", "absent"),
    ]:
        with pytest.raises(ValueError):
            plan(
                inspect_source(source, module_name="ineligible"),
                source,
                capability,
                ExecutionPolicy(),
            )
