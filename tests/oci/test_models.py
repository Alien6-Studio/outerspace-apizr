import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.capabilities.model import Digest
from apizr.execution import ExecutionPolicy, policy_bytes
from apizr.execution.policy import PolicyRefused, Subprocess
from apizr.execution.serialization import canonical_bytes
from apizr.oci.model import ExecutionPolicyV2, Resources, RuntimeImage
from apizr.oci.planner import validate_plan
from apizr.oci.supervisor import execute

from .helpers import IMAGE, planned


@pytest.mark.parametrize(
    "field,value",
    [
        ("memory_bytes", 1024),
        ("memory_bytes", True),
        ("cpu_millis", 0),
        ("cpu_millis", 0.5),
        ("cpu_millis", 64001),
        ("pids", 0),
        ("pids", 1025),
        ("scratch_bytes", 0),
        ("scratch_bytes", 268435456),
    ],
)
def test_invalid_resource_bounds(field, value):
    with pytest.raises(ValueError):
        Resources.model_validate({field: value})


@pytest.mark.parametrize(
    "image",
    ["python:3.14-slim", "sha256:abc", "repo@sha256:" + "a" * 64, "SHA256:" + "a" * 64],
)
def test_full_local_image_identity_required(image):
    with pytest.raises(ValueError):
        RuntimeImage(image=image, platform="linux/amd64")


@pytest.mark.parametrize(
    "change",
    [
        {"network": {"mode": "inherit"}},
        {"environment": {"inherit": True}},
        {"subprocess": {"mode": "deny"}},
        {"effects": {"require_known": ["network"]}},
    ],
)
def test_fail_closed_controls_and_unknown_effects(change):
    with pytest.raises(PolicyRefused):
        planned(**change)


def test_v2_does_not_accept_provider_escape_hatches_or_v1():
    for document in [
        {"extra_args": ["--privileged"]},
        {"mounts": ["/"]},
        {"schema_version": "apizr.execution/v1"},
    ]:
        with pytest.raises(ValueError):
            ExecutionPolicyV2.model_validate(document)
    with pytest.raises(ValueError):
        ExecutionPolicy.model_validate_json(canonical_bytes(ExecutionPolicyV2()))
    assert b"apizr.execution/v1" in policy_bytes(ExecutionPolicy())


def test_golden_and_host_independent_plan(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("static planning attempted runtime discovery/execution")

    monkeypatch.setattr("subprocess.Popen", forbidden)
    monkeypatch.setattr("socket.socket", forbidden)
    value, raw = planned()
    fixture = Path(__file__).parents[1] / "fixtures/oci"
    assert canonical_bytes(value) == (fixture / "plan.json").read_bytes()
    assert canonical_bytes(value.policy) == (fixture / "policy.json").read_bytes()
    assert validate_plan(value, raw, raw) == value
    assert value.worker.policy.network.mode == "inherit"  # Only inner worker claims.
    assert value.policy.network.mode == "deny"  # Enforced by provider, not Python.
    assert json.loads(canonical_bytes(value))["runtime"]["image"] == IMAGE.image


@settings(max_examples=15, deadline=None)
@given(st.integers(10, 2000), st.lists(st.sampled_from(["LANG", "TOKEN"]), max_size=4))
def test_plan_determinism_and_control_binding(cpu, names):
    first, _ = planned(resources={"cpu_millis": cpu}, environment={"allow": names})
    second, _ = planned(
        environment={"allow": list(reversed(names))}, resources={"cpu_millis": cpu}
    )
    assert canonical_bytes(first) == canonical_bytes(second)
    assert first.policy_digest == Digest.of_bytes(canonical_bytes(first.policy))
    assert first.worker_digest == Digest.of_bytes(canonical_bytes(first.worker))


@pytest.mark.parametrize(
    "field", ["policy_digest", "worker_digest", "runtime", "worker", "policy"]
)
def test_tampered_plan_rejected_before_provider(field):
    value, raw = planned()
    replacement = {
        "policy_digest": Digest.of_bytes(b"bad"),
        "worker_digest": Digest.of_bytes(b"bad"),
        "runtime": IMAGE.model_copy(update={"image": "mutable"}),
        "worker": value.worker.model_copy(
            update={"interface_digest": Digest.of_bytes(b"bad")}
        ),
        "policy": value.policy.model_copy(
            update={"resources": Resources(cpu_millis=500)}
        ),
    }[field]
    assert (
        execute(value.model_copy(update={field: replacement}), raw, {}).status
        == "binding_failed"
    )


def test_invalid_source_arguments_and_refused_policy():
    value, raw = planned("def f(x:int): return x")
    assert execute(value, raw + b"\n", {"x": 1}).status == "binding_failed"
    assert execute(value, raw, {"x": None}).status == "invalid_input"
    denied = value.policy.model_copy(update={"subprocess": Subprocess(mode="deny")})
    assert (
        execute(value.model_copy(update={"policy": denied}), raw, {}).status
        == "policy_refused"
    )
