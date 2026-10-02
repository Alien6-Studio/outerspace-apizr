"""Reject implicit or expanded Homebrew qualification claims."""

import copy
import json
import runpy
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
tool = runpy.run_path(str(ROOT / "scripts/check_homebrew_qualification.py"))
inputs = runpy.run_path(str(ROOT / "scripts/prepare_homebrew_build_inputs.py"))


def policy_and_manifest():
    policy = json.loads((ROOT / "policy/homebrew-qualification.json").read_text())
    manifest = inputs["encoded"](
        inputs["manifest"](ROOT / "uv.lock", ROOT / "policy/homebrew-build-inputs.json")
    )
    return policy, manifest


def test_homebrew_boundary_is_explicit_deterministic_and_preserves_build_identity():
    policy, manifest = policy_and_manifest()
    result = tool["validate"](policy, manifest)
    assert policy["qualification"]["required"] == ["macos-arm64-tier1"]
    assert policy["qualification"]["not_qualified"] == [
        {"platform": "macos-x86_64", "reason": "homebrew-tier3"},
        {"platform": "linux", "reason": "runtime-not-qualified-in-0.4.2"},
    ]
    assert policy["build_inputs_manifest_sha256"] == (
        "aa130065b43006d90a6ee9d54ab755b68a85be7ec837a7c08ff3e20e611011ef"
    )
    reordered = dict(reversed(list(policy.items())))
    assert tool["encoded"](result) == tool["encoded"](
        tool["validate"](reordered, manifest)
    )
    assert str(ROOT).encode() not in tool["encoded"](result)


@pytest.mark.parametrize(
    "change",
    [
        "unknown",
        "duplicate-required",
        "duplicate-excluded",
        "conflict",
        "missing",
        "implicit-all",
        "wrong-reason",
        "extra-field",
    ],
)
def test_unreviewed_platform_classifications_are_rejected(change):
    policy, manifest = policy_and_manifest()
    qualification = policy["qualification"]
    if change == "unknown":
        qualification["required"].append("windows-arm64")
    elif change == "duplicate-required":
        qualification["required"] *= 2
    elif change == "duplicate-excluded":
        qualification["not_qualified"].append(
            copy.deepcopy(qualification["not_qualified"][0])
        )
    elif change == "conflict":
        qualification["required"].append("macos-x86_64")
    elif change == "missing":
        qualification["not_qualified"].pop()
    elif change == "implicit-all":
        policy["qualification"] = {}
    elif change == "wrong-reason":
        qualification["not_qualified"][0]["reason"] = "qualified"
    else:
        qualification["default"] = "qualified"
    with pytest.raises(ValueError, match="platform qualification"):
        tool["validate"](policy, manifest)


def test_vm_cannot_be_claimed_as_physical_tier1_evidence():
    policy, manifest = policy_and_manifest()
    policy["evidence"]["ci"]["host"] = "physical-apple-silicon"
    with pytest.raises(ValueError, match="evidence boundary"):
        tool["validate"](policy, manifest)
    policy, manifest = policy_and_manifest()
    policy["evidence"]["physical_mac"]["required"] = False
    with pytest.raises(ValueError, match="evidence boundary"):
        tool["validate"](policy, manifest)


def test_unversioned_policy_and_substituted_build_manifest_are_rejected():
    policy, manifest = policy_and_manifest()
    with pytest.raises(ValueError, match="identity changed"):
        tool["validate"](policy, manifest + b"\n")
    del policy["schema"]
    with pytest.raises(ValueError, match="schema"):
        tool["validate"](policy, manifest)


def test_required_workflow_matches_the_explicit_arm64_boundary():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/homebrew-build-inputs.yml").read_text()
    )
    jobs = workflow["jobs"]
    assert set(jobs) == {"candidate", "offline-build-arm64"}
    job = jobs["offline-build-arm64"]
    policy, _ = policy_and_manifest()
    assert job["runs-on"] == policy["evidence"]["ci"]["runner"]
    assert "strategy" not in job
    assert "continue-on-error" not in json.dumps(workflow)
    assert any(
        "check_homebrew_qualification.py" in step.get("run", "")
        for step in jobs["candidate"]["steps"]
    )
