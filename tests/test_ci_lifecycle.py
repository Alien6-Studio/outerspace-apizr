"""Protect PR supersession without cancelling retained qualification evidence."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = []
for path in sorted((ROOT / ".github/workflows").glob("*.y*ml")):
    workflow = yaml.safe_load(path.read_text())
    if "pull_request" in workflow.get("on", workflow.get(True, {})):
        WORKFLOWS.append((path.name, workflow))


@pytest.mark.parametrize(
    "name,workflow", WORKFLOWS, ids=[name for name, _ in WORKFLOWS]
)
def test_supersession_is_bound_to_one_pr_and_one_workflow(name, workflow):
    # PR numbers are unique even when fork branches have the same name. Other
    # events use run_id: pending push/dispatch/schedule runs never share a group.
    assert all("always()" not in job.get("if", "") for job in workflow["jobs"].values())
    concurrency = workflow["concurrency"]
    assert concurrency["group"] == (
        "${{ github.workflow }}-${{ github.event_name }}-"
        "${{ github.event.pull_request.number || github.run_id }}"
    )
    assert (
        concurrency["cancel-in-progress"]
        == "${{ github.event_name == 'pull_request' }}"
    )


@pytest.mark.parametrize(
    "name,workflow", WORKFLOWS, ids=[name for name, _ in WORKFLOWS]
)
def test_pr_artifact_retention_preserves_qualification_evidence(name, workflow):
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if not step.get("uses", "").startswith("actions/upload-artifact@"):
                continue
            if name == "mkdocs.yaml":
                # This artifact is only a master deployment input, never a PR
                # proof; retain the existing publication policy unchanged.
                assert (
                    step["if"]
                    == "github.event_name == 'push' && github.ref == 'refs/heads/master'"
                )
                assert step["with"]["retention-days"] == 7
            else:
                assert step["with"]["retention-days"] == (
                    "${{ github.event_name == 'pull_request' && 7 || 90 }}"
                )


def test_retired_branch_triggers_are_absent_and_manual_reruns_remain():
    for _, workflow in WORKFLOWS:
        events = workflow.get("on", workflow.get(True, {}))
        assert "workflow_dispatch" in events
        for branch in (events.get("push") or {}).get("branches", []):
            assert not branch.startswith(("feature/", "fix/", "chore/"))


def test_dependabot_groups_compatible_updates_and_all_codeql_steps():
    settings = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())
    updates = {item["package-ecosystem"]: item for item in settings["updates"]}
    assert updates["uv"]["groups"] == {
        "compatible-updates": {"update-types": ["minor", "patch"]}
    }
    assert updates["github-actions"]["schedule"]["interval"] == "monthly"
    assert updates["github-actions"]["groups"] == {
        "action-updates": {"patterns": ["*"]}
    }
