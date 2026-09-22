import json

import pytest

from apizr.capabilities.model import Digest
from apizr.execution.policy import ExecutionPolicy, PolicyRefused
from apizr.execution.serialization import digest
from apizr.oci.model import ExecutionPolicyV2, RuntimeImage
from apizr.repository_execution.model import (
    RepositoryContainerPlan,
    RepositoryRuntimePlan,
)
from apizr.repository_execution.planner import (
    container_plan,
    validate_plan,
    validate_sources,
    worker_plan,
)

from .helpers import IMAGE, planned


@pytest.mark.parametrize("policy", [ExecutionPolicy(), ExecutionPolicyV2()])
def test_independent_contracts_and_validation(policy):
    plan, exposure, sources, _ = planned(policy=policy)
    worker = plan.worker if isinstance(plan, RepositoryContainerPlan) else plan
    assert worker.schema_version == "apizr.repository-runtime/v1"
    assert not hasattr(worker, "inspection") and not hasattr(worker, "source")
    assert worker.repository_interface_digest == digest(worker.repository_interface)
    assert worker.interface_digest == digest(worker.interface)
    assert worker.execution_context == policy.backend
    assert RepositoryRuntimePlan.model_validate_json(worker.model_dump_json()) == worker
    validate_plan(plan, exposure)
    validate_sources(worker.repository_interface, sources)
    if isinstance(plan, RepositoryContainerPlan):
        assert (
            plan.schema_version == "apizr.repository-runtime/v2"
            and plan.worker_digest == digest(worker)
        )


@pytest.mark.parametrize(
    "kind",
    ["digest", "interface", "policy", "effects", "source_universe", "worker_digest"],
)
def test_forged_plans_refused(kind):
    plan, exposure, _, _ = planned(
        policy=ExecutionPolicyV2() if kind == "worker_digest" else ExecutionPolicy()
    )
    field = {
        "digest": "interface_digest",
        "interface": "repository_interface_digest",
        "policy": "policy_digest",
        "effects": "exposure_plan_digest",
        "source_universe": "source_universe_digest",
        "worker_digest": "worker_digest",
    }[kind]
    with pytest.raises(ValueError):
        validate_plan(
            plan.model_copy(update={field: Digest.of_bytes(b"forged")}), exposure
        )


@pytest.mark.parametrize(
    "control",
    [
        {"network": {"mode": "deny"}},
        {"filesystem": {"mode": "sandbox"}},
        {"subprocess": {"mode": "deny"}},
    ],
)
def test_unsupported_local_controls_refused(control):
    with pytest.raises(PolicyRefused, match="unsupported_control"):
        planned(policy=ExecutionPolicy.model_validate(control))


@pytest.mark.parametrize(
    "control",
    [
        {"network": {"mode": "inherit"}},
        {"environment": {"inherit": True}},
        {"subprocess": {"mode": "deny"}},
    ],
)
def test_unsupported_oci_controls_refused(control):
    with pytest.raises(PolicyRefused):
        planned(policy=ExecutionPolicyV2.model_validate(control))


def test_effect_require_known_uses_bound_snapshot():
    with pytest.raises(PolicyRefused, match="unknown_required_effect"):
        planned(
            policy=ExecutionPolicy.model_validate(
                {"effects": {"require_known": ["network"]}}
            )
        )


def test_no_policy_widening_no_unknown_capability():
    plan, exposure, _, _ = planned()
    with pytest.raises(PolicyRefused, match="repository_backend_incompatible"):
        container_plan(
            plan.repository_interface,
            exposure,
            plan.capability_id,
            ExecutionPolicyV2(),
            IMAGE,
        )
    with pytest.raises(ValueError, match="not exposed"):
        worker_plan(
            plan.repository_interface, exposure, "python:sample.api:helper", plan.policy
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "raw",
        "schema",
        "interfaces",
        "repository_digest",
        "selection",
        "mode",
        "module",
        "path",
    ],
)
def test_exposure_binding(mutation):
    plan, raw, _, _ = planned()
    doc = json.loads(raw)
    contract = plan.repository_interface
    if mutation == "raw":
        raw += b" "
    else:
        if mutation == "schema":
            doc["schema_version"] = "wrong"
        elif mutation == "interfaces":
            doc["interfaces"] = ["mcp"]
        elif mutation == "repository_digest":
            doc["repository_digest"] = Digest.of_bytes(b"wrong").model_dump()
        elif mutation == "selection":
            doc["capabilities"] = []
        elif mutation == "mode":
            doc["capabilities"][0]["compatible_execution_modes"] = ["direct"]
        elif mutation == "module":
            doc["capabilities"][0]["module"] = "other"
        else:
            doc["capabilities"][0]["source_path"] = "other.py"
        raw = json.dumps(doc).encode()
        contract = contract.model_copy(
            update={"exposure_plan_digest": Digest.of_bytes(raw)}
        )
    with pytest.raises(ValueError):
        worker_plan(contract, raw, plan.capability_id, plan.policy)


@pytest.mark.parametrize("change", ["missing", "extra", "digest", "type"])
def test_exact_sources(change):
    plan, _, sources, _ = planned()
    if change == "missing":
        sources.pop(next(iter(sources)))
    elif change == "extra":
        sources["extra.py"] = b""
    elif change == "digest":
        sources[next(iter(sources))] += b" "
    else:
        sources[next(iter(sources))] = "not bytes"
    with pytest.raises(ValueError):
        validate_sources(plan.repository_interface, sources)


def test_no_runtime_probe_during_planning(monkeypatch):
    import apizr.execution.policy as policy
    from apizr.repository_execution.docker import RepositoryDockerProvider

    def forbidden(*args):
        raise AssertionError("probe")

    monkeypatch.setattr(policy, "local_capabilities", forbidden)
    monkeypatch.setattr(RepositoryDockerProvider, "probe", forbidden)
    planned()
    planned(policy=ExecutionPolicyV2())


@pytest.mark.parametrize(
    "image,platform",
    [
        ("latest", "linux/amd64"),
        ("sha256:short", "linux/amd64"),
        ("sha256:" + "0" * 64, "host"),
    ],
)
def test_immutable_image_required(image, platform):
    with pytest.raises(ValueError):
        RuntimeImage(image=image, platform=platform)
