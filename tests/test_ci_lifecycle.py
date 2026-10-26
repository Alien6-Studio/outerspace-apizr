"""Protect PR supersession without cancelling retained qualification evidence."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFINITIONS = {}
for path in sorted((ROOT / ".github/workflows").glob("*.y*ml")):
    DEFINITIONS[path.name] = yaml.safe_load(path.read_text())
CALLEES = {
    Path(job["uses"]).name
    for name, job in DEFINITIONS["ci.yml"]["jobs"].items()
    if name != "scope" and job.get("uses", "").startswith("./.github/workflows/")
}
WORKFLOWS = [
    (name, workflow)
    for name, workflow in DEFINITIONS.items()
    if name == "ci.yml" or name in CALLEES
]


@pytest.mark.parametrize(
    "name,workflow", WORKFLOWS, ids=[name for name, _ in WORKFLOWS]
)
def test_supersession_is_bound_to_one_pr_and_one_workflow(name, workflow):
    # PR numbers are unique even when fork branches have the same name. Other
    # events use run_id: pending push/dispatch/schedule runs never share a group.
    assert all("always()" not in job.get("if", "") for job in workflow["jobs"].values())
    concurrency = workflow["concurrency"]
    prefix = "${{ github.workflow }}" if name == "ci.yml" else workflow["name"]
    assert concurrency["group"] == (
        prefix + "-${{ github.event_name }}-"
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
            if name == "mkdocs.yaml" and step["with"]["name"] == "documentation-site":
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


def test_only_ci_receives_pr_and_development_push_events():
    assert [
        name
        for name, workflow in DEFINITIONS.items()
        if "pull_request" in workflow.get("on", workflow.get(True, {}))
    ] == ["ci.yml"]
    ci = DEFINITIONS["ci.yml"]
    events = ci.get("on", ci.get(True, {}))
    assert events["push"] == {"branches": ["master", "0.4.6"]}
    assert "workflow_dispatch" in events


def test_preparation_is_qualified_by_mcp_without_a_second_push_run():
    mcp = yaml.safe_load((ROOT / ".github/workflows/mcp-server-plugin.yml").read_text())
    assert (
        mcp["jobs"]["preparation-qualification"]["uses"]
        == "./.github/workflows/plugin-preparation-qualification.yml"
    )
    preparation = yaml.safe_load(
        (ROOT / ".github/workflows/plugin-preparation-qualification.yml").read_text()
    )
    events = preparation.get("on", preparation.get(True, {}))
    assert set(events) == {"workflow_call", "workflow_dispatch", "schedule"}


def test_dependabot_groups_compatible_updates_and_all_codeql_steps():
    settings = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())
    updates = {
        (item["package-ecosystem"], item.get("target-branch")): item
        for item in settings["updates"]
    }
    assert updates[("uv", None)]["groups"] == {
        "compatible-updates": {"update-types": ["minor", "patch"]}
    }
    assert updates[("github-actions", None)]["schedule"]["interval"] == "monthly"
    assert updates[("github-actions", None)]["groups"] == {
        "action-updates": {"patterns": ["*"]}
    }
    assert updates[("uv", "gh-pages")]["groups"] == {
        "website-tooling": {"update-types": ["minor", "patch"]}
    }
    assert updates[("github-actions", "gh-pages")]["groups"] == {
        "website-actions": {"patterns": ["*"]}
    }
    assert updates[("npm", None)]["schedule"]["interval"] == "weekly"
    assert updates[("npm", None)]["groups"] == {
        "client-tooling": {"update-types": ["minor", "patch"]}
    }
    assert {key: item["directory"] for key, item in updates.items()} == {
        ("uv", None): "/",
        ("github-actions", None): "/",
        ("npm", None): "/scripts/client_collection_tools",
        ("uv", "gh-pages"): "/",
        ("github-actions", "gh-pages"): "/",
    }


def test_final_candidate_includes_one_shared_editor_and_signed_evidence():
    jobs = DEFINITIONS["ci.yml"]["jobs"]
    distributions = jobs["distributions"]["steps"]
    assert any(
        s.get("uses", "").startswith("actions/setup-node@") for s in distributions
    )
    vscode = jobs["vscode"]
    assert "github.ref != 'refs/heads/master'" not in vscode["if"]
    commands = "\n".join(s.get("run", "") for s in vscode["steps"])
    assert '--output "$RUNNER_TEMP/vscode-dist"\n' not in commands
    assert 'cp "$RUNNER_TEMP/vscode-candidate/editor/"*' in commands
    assert any(
        s.get("with", {}).get("name") == "release-editor" for s in vscode["steps"]
    )
    for name in ("provenance", "release-assets"):
        assert "vscode" in jobs[name]["needs"]
    assert "needs.vscode.result == 'success'" in jobs["release-assets"]["if"]
    attest = next(s for s in jobs["provenance"]["steps"] if s.get("id") == "provenance")
    assert "editor/*.vsix" in attest["with"]["subject-path"]
