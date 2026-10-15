"""Shared scope/candidates must preserve routing, source identity and check failures."""

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"


def load(name):
    return yaml.safe_load((WORKFLOWS / name).read_text())


def allows(
    condition,
    *,
    product,
    examples,
    distribution,
    scope="success",
    ref="refs/heads/0.4.6",
):
    """Evaluate the actual bounded routing expression, using synthetic job results."""
    expression = condition.removeprefix("${{").removesuffix("}}").strip()
    expression = (
        expression.replace("!cancelled()", "True")
        .replace("&&", "and")
        .replace("||", "or")
    )
    needs = SimpleNamespace(
        scope=SimpleNamespace(
            result=scope, outputs=SimpleNamespace(product=product, examples=examples)
        ),
        distributions=SimpleNamespace(result=distribution),
    )
    return eval(
        expression,
        {"__builtins__": {}},
        {"needs": needs, "github": SimpleNamespace(ref=ref)},
    )


def test_reusable_groups_cannot_cancel_the_caller_or_each_other():
    ci = load("ci.yml")
    calls = [
        job for job in ci["jobs"].values() if job.get("with", {}).get("scope_ready")
    ]
    assert len(calls) == 13
    groups = []
    for job in calls:
        child = load(Path(job["uses"]).name)
        events = child.get("on", child.get(True, {}))
        assert "pull_request" not in events
        assert "0.4.6" not in events.get("push", {}).get("branches", [])
        assert set(events) >= {"workflow_call", "workflow_dispatch"}
        group = child["concurrency"]["group"]
        assert "github.workflow" not in group
        assert (
            child["concurrency"]["cancel-in-progress"]
            == "${{ github.event_name == 'pull_request' }}"
        )
        groups.append(group)
        if "scope" in child["jobs"]:
            assert child["jobs"]["scope"]["if"] == "${{ !inputs.scope_ready }}"
    assert len(set(groups)) == len(groups)


@pytest.mark.parametrize(
    "product,examples,distribution,expected",
    [
        ("false", "false", "skipped", True),
        ("false", "true", "skipped", True),
        ("true", "true", "success", True),
        ("true", "true", "failure", False),
        ("true", "true", "skipped", False),
        ("false", "false", "failure", False),
    ],
)
def test_documentation_examples_survive_web_only_routing_without_product_build(
    product, examples, distribution, expected
):
    job = load("ci.yml")["jobs"]["mkdocs-qualification"]
    assert (
        allows(job["if"], product=product, examples=examples, distribution=distribution)
        is expected
    )
    assert not allows(
        job["if"],
        product=product,
        examples=examples,
        distribution=distribution,
        scope="failure",
    )
    assert not allows(
        job["if"],
        product=product,
        examples=examples,
        distribution=distribution,
        ref="refs/heads/master",
    )


@pytest.mark.parametrize("context", ["dependencies", "codeql", "build"])
@pytest.mark.parametrize(
    "scope,product,result,expected",
    [
        ("success", "true", "success", True),
        ("success", "true", "failure", False),
        ("success", "true", "skipped", False),
        ("failure", "true", "success", False),
        ("success", "false", "skipped", True),
        ("success", "unknown", "success", False),
    ],
)
def test_protected_result_jobs_refuse_missing_failed_or_skipped_product_proofs(
    context, scope, product, result, expected
):
    job = load("ci.yml")["jobs"][context]
    script = job["steps"][0]["run"]
    run = subprocess.run(
        ["bash", "-e", "-c", script],
        env={
            **os.environ,
            "SCOPE_RESULT": scope,
            "PRODUCT_CHECKS": product,
            "QUALIFICATION_RESULT": result,
        },
        capture_output=True,
        timeout=10,
    )
    # Documentation always runs a real build, including web-only changes.
    if context == "build":
        expected = scope == "success" and result == "success"
    assert (run.returncode == 0) is expected
    assert "external-" + context in job["name"]
    assert "github.ref != 'refs/heads/master'" in job["if"]


def test_shared_candidates_stay_in_the_same_run_and_bind_to_the_checkout():
    ci = load("ci.yml")
    for key in (
        "forge-integrations-qualification",
        "homebrew-formula-qualification",
        "homebrew-build-inputs-qualification",
        "mkdocs-qualification",
    ):
        caller = ci["jobs"][key]
        assert "distributions" in caller["needs"]
        assert "needs.distributions.result == 'success'" in caller["if"]
        assert "release-candidate" in caller["with"]["candidate_artifact"]
        assert (
            "qualification_layout != 'independent'"
            in caller["with"]["candidate_artifact"]
        )
        child = load(Path(caller["uses"]).name)
        for job in child["jobs"].values():
            for step in job.get("steps", []):
                if step.get("uses", "").startswith("actions/download-artifact@"):
                    assert not (
                        {"run-id", "github-token", "repository"} & step["with"].keys()
                    )
                if step.get("uses", "").startswith(
                    "actions/checkout@"
                ) and "ref" in step.get("with", {}):
                    assert "inputs.scope_ready && github.sha" in step["with"]["ref"]


def test_master_security_publication_and_development_read_permissions_stay_separate():
    docs = load("mkdocs.yaml")
    security = load("security.yml")
    for workflow in (docs, security):
        events = workflow.get("on", workflow.get(True, {}))
        assert events["push"] == {"branches": ["master"]}
    assert "schedule" in security.get("on", security.get(True, {}))
    assert docs["jobs"]["build"]["permissions"] == {"contents": "read"}
    assert "github.ref == 'refs/heads/master'" in docs["jobs"]["deploy"]["if"]
    assert docs["jobs"]["deploy"]["concurrency"] == {
        "group": "documentation-publication",
        "cancel-in-progress": False,
    }


@pytest.mark.parametrize(
    "candidate,cancelled,expected",
    [
        ("success", False, True),
        ("failure", False, False),
        ("skipped", False, False),
        ("cancelled", False, False),
        ("success", True, False),
    ],
)
def test_offline_homebrew_proof_survives_the_intentionally_skipped_local_scope(
    candidate, cancelled, expected
):
    job = load("homebrew-build-inputs.yml")["jobs"]["offline-build-arm64"]
    assert job["needs"] == "candidate"
    # GitHub otherwise propagates the skipped scope through candidate's needs.
    assert "!cancelled()" in job["if"]
    condition = (
        job["if"]
        .removeprefix("${{")
        .removesuffix("}}")
        .strip()
        .replace("!cancelled()", str(not cancelled))
        .replace("&&", "and")
    )
    needs = SimpleNamespace(candidate=SimpleNamespace(result=candidate))
    assert eval(condition, {"__builtins__": {}}, {"needs": needs}) is expected
