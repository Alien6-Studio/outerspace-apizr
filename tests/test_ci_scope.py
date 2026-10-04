"""Web routing must never hide product changes or lose required check contexts."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ci_scope", ROOT / "scripts/ci_scope.py")
assert spec and spec.loader
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def commit(root, name, content="content"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    git(root, "add", "--", name)
    git(root, "commit", "-qm", "fixture")
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q", "-b", "master")
    git(tmp_path, "config", "user.name", "CI fixture")
    git(tmp_path, "config", "user.email", "ci@example.invalid")
    git(tmp_path, "config", "commit.gpgsign", "false")
    commit(tmp_path, "src/product.py")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def event(base, head):
    return {"ref": "refs/heads/master", "before": base, "after": head}


def pr_event(base, head):
    return {
        "pull_request": {"base": {"sha": base, "ref": "master"}, "head": {"sha": head}}
    }


@pytest.mark.parametrize(
    "name,examples",
    [
        ("docs/index.md", "false"),
        ("docs/nested/page with\na newline.md", "false"),
        ("docs/assets/stylesheets/branding.css", "false"),
        ("docs/assets/javascripts/video.js", "false"),
        ("docs/assets/videos/demo.mp4", "false"),
        ("docs/assets/images/logo.png", "false"),
        ("overrides/partials/source.html", "false"),
        *[(name, "true") for name in sorted(scope.EXAMPLE_PAGES)],
    ],
)
def test_web_changes_use_only_relevant_checks(repo, name, examples):
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, name)
    for kind, payload in (
        ("push", event(base, head)),
        ("pull_request", pr_event(base, head)),
    ):
        result = scope.classify(kind, payload)
        assert result["product"] == "false"
        assert result["examples"] == examples


@pytest.mark.parametrize(
    "name",
    [
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
        "pyproject.toml",
        "uv.lock",
        "mkdocs.yml",
        "docs/CNAME",
        "docs/hook.py",
        "overrides/hook.py",
        "scripts/ci_scope.py",
        "tests/test_product.py",
        "src/product.py",
        "plugins/mcp/README.md",
        ".github/workflows/ci.yml",
        "unknown.txt",
    ],
)
def test_mixed_pr_keeps_full_qualification_even_after_a_final_docs_commit(repo, name):
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, name, "changed")
    head = commit(repo, "docs/index.md")
    assert scope.classify("pull_request", pr_event(base, head))["product"] == "true"


def test_pr_uses_merge_base_not_unrelated_target_changes(repo):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-qb", "web")
    head = commit(repo, "docs/index.md")
    git(repo, "checkout", "-q", "master")
    new_base = commit(repo, "src/product.py", "unrelated target change")
    assert new_base != base
    assert (
        scope.classify("pull_request", pr_event(new_base, head))["product"] == "false"
    )


def test_moving_product_into_docs_still_requires_product_checks(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "docs").mkdir()
    git(repo, "mv", "src/product.py", "docs/product.md")
    git(repo, "commit", "-qm", "move")
    assert (
        scope.classify("push", event(base, git(repo, "rev-parse", "HEAD")))["product"]
        == "true"
    )


def test_deleted_web_page_can_use_web_checks(repo):
    base = commit(repo, "docs/obsolete.md")
    git(repo, "rm", "-q", "docs/obsolete.md")
    git(repo, "commit", "-qm", "delete")
    assert (
        scope.classify("push", event(base, git(repo, "rev-parse", "HEAD")))["product"]
        == "false"
    )


@pytest.mark.parametrize("mode", ["symlink", "executable"])
def test_non_regular_web_paths_require_full_checks(repo, mode):
    base = git(repo, "rev-parse", "HEAD")
    path = repo / "docs/index.md"
    path.parent.mkdir()
    if mode == "symlink":
        path.symlink_to("../src/product.py")
    else:
        path.write_text("executable")
        path.chmod(0o755)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "special file")
    assert (
        scope.classify("push", event(base, git(repo, "rev-parse", "HEAD")))["product"]
        == "true"
    )


def test_no_api_file_limit_hides_product_changes(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "docs").mkdir()
    for i in range(350):
        (repo / f"docs/{i}.md").write_text("page")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "many pages")
    head = commit(repo, "src/product.py", "also changed")
    assert scope.classify("push", event(base, head))["product"] == "true"


def test_missing_empty_manual_and_release_comparisons_run_full_checks(repo):
    sha = git(repo, "rev-parse", "HEAD")
    cases = [
        ("push", event(sha, sha)),
        ("push", event("0" * 40, sha)),
        ("push", event("f" * 40, sha)),
        ("push", {}),
        ("push", event("--help", sha)),
        ("pull_request", {}),
        ("workflow_dispatch", {}),
        ("schedule", {}),
    ]
    head = commit(repo, "docs/index.md")
    release_pr = pr_event(sha, head)
    release_pr["pull_request"]["base"]["ref"] = "release/0.5"
    cases += [
        ("pull_request", release_pr),
        ("push", event(sha, head) | {"ref": "refs/heads/release/0.5"}),
    ]
    for kind, payload in cases:
        result = scope.classify(kind, payload)
        assert result["product"] == result["examples"] == "true"


def test_cli_invalid_event_defaults_to_full_checks(repo, monkeypatch):
    payload, output = repo / "event.json", repo / "output"
    payload.write_text("invalid JSON")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(payload))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    scope.main()
    assert "product=true\nexamples=true\n" in output.read_text()


def test_required_matrix_checks_are_emitted_for_web_changes():
    # A job-level false condition is evaluated before matrix expansion and can
    # leave the required version-specific contexts missing. Gate steps instead.
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    for name, versions in (
        ("compatibility", ["3.11", "3.12", "3.13", "3.14"]),
        ("container", ["3.11", "3.12", "3.13", "3.14"]),
        ("macos", ["3.11", "3.14"]),
    ):
        job = workflow["jobs"][name]
        assert job["if"] == "always()"
        assert job["strategy"]["matrix"]["python"] == versions
        assert all("needs.scope.outputs.product" in step["if"] for step in job["steps"])
    assert "ubuntu-latest" in workflow["jobs"]["macos"]["runs-on"]
    assert workflow["jobs"]["quality"]["if"] == "always()"


def test_web_allowlist_does_not_overlap_published_sources():
    # The root README and plugin READMEs belong to distributions, not just the site.
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    paths = project["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert all(not scope.web_path(path.lstrip("/")) for path in paths)


def test_all_pr_qualification_workflows_share_the_scope_gate():
    for path in (ROOT / ".github/workflows").glob("*.y*ml"):
        workflow = yaml.safe_load(path.read_text())
        events = workflow.get("on", workflow.get(True, {}))
        if (
            "pull_request" not in events
            or path.name == "governed-rest-qualification.yml"
        ):
            continue
        assert (
            workflow["jobs"]["scope"]["uses"] == "./.github/workflows/change-scope.yml"
        )
        assert not (events["pull_request"] or {}).get("paths-ignore")


def test_scope_summary_and_outputs(repo, monkeypatch):
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, "docs/index.md")
    payload, output, summary = repo / "event.json", repo / "output", repo / "summary"
    payload.write_text(json.dumps(event(base, head)))
    for key, value in {
        "GITHUB_EVENT_PATH": payload,
        "GITHUB_OUTPUT": output,
        "GITHUB_STEP_SUMMARY": summary,
        "GITHUB_EVENT_NAME": "push",
    }.items():
        monkeypatch.setenv(key, str(value))
    scope.main()
    assert "product=false\nexamples=false\n" in output.read_text()
    assert "Only allowlisted web content changed" in summary.read_text()
