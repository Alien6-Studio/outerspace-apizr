"""Documentation routing must retain product qualification for mixed changes."""

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
        ("README.md", "true"),
        ("CHANGELOG.md", "false"),
        ("CONTRIBUTING.md", "false"),
        ("mkdocs.yml", "true"),
        ("docs/CNAME", "false"),
        ("docs/robots.txt", "false"),
        ("docs/assets/videos/uv-install.tape", "true"),
        ("docs/examples/operator.json", "true"),
        ("tools/docs/pyproject.toml", "false"),
        ("tools/docs/uv.lock", "false"),
        ("scripts/docs_build.py", "true"),
        ("scripts/check_docs_html.py", "false"),
        ("scripts/check_docs_site.py", "false"),
        ("scripts/smoke_site_examples.py", "true"),
        ("scripts/smoke_readme.py", "true"),
        ("scripts/site_example_packages.py", "true"),
        ("scripts/typed_dict_proof.py", "true"),
        ("tools/docs/README.md", "false"),
        ("tests/test_docs_publication.py", "false"),
        ("tests/test_site_refonte.py", "false"),
        ("review/architecture-guide.md", "false"),
        ("review/site-refonte/page-migration.json", "false"),
        ("examples/repository-shop/quote-service/src/api.py", "true"),
        ("examples/data-science/fraud-detection/fraud_detection.ipynb", "true"),
        ("examples/extension-probe/pyproject.toml", "true"),
        ("docs/start/index.md", "true"),
        ("docs/examples/business-quote.md", "true"),
        ("docs/developer-guide/compiler.md", "true"),
        ("docs/user-guide/select-functions.md", "true"),
        ("docs/operations-guide/local-service.md", "true"),
        ("docs/getting-started/data-science.md", "true"),
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
        "LICENSE",
        "pyproject.toml",
        "uv.lock",
        "docs/hook.py",
        "docs/specs/apizr-capability-v1.schema.json",
        "overrides/hook.py",
        "scripts/ci_scope.py",
        "scripts/coordinated_distributions.py",
        "scripts/check_distribution.py",
        "scripts/security_mutations.py",
        "scripts/smoke_oci_registry.py",
        "tests/test_ci_scope.py",
        "tests/conftest.py",
        "tests/test_product.py",
        "src/product.py",
        "plugins/mcp/README.md",
        ".github/workflows/ci.yml",
        ".github/workflows/change-scope.yml",
        ".github/workflows/mkdocs.yaml",
        ".github/actions/install-attest/action.yml",
        "tools/docs/hook.py",
        "review/tool.py",
        "review/unknown.json",
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
@pytest.mark.parametrize(
    "name", ["docs/index.md", "examples/fixture.py", "scripts/docs_build.py"]
)
def test_non_regular_web_paths_require_full_checks(repo, mode, name):
    base = git(repo, "rev-parse", "HEAD")
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
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


def test_documentation_allowlist_excludes_published_implementation():
    # Textual root metadata may use the documentation path; implementation,
    # package configuration, license and plugin sources still require product CI.
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    paths = project["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert {
        path.lstrip("/") for path in paths if scope.documentation_path(path.lstrip("/"))
    } == {"README.md", "CHANGELOG.md"}


def test_complete_site_revision_uses_documentation_checks(repo):
    base = git(repo, "rev-parse", "HEAD")
    for name in (
        "README.md",
        "mkdocs.yml",
        "docs/architecture/index.md",
        "scripts/docs_build.py",
        "scripts/check_docs_html.py",
        "tests/test_site_refonte.py",
        "review/site-refonte/page-migration.json",
        "review/architecture-guide.md",
    ):
        commit(repo, name)
    head = git(repo, "rev-parse", "HEAD")
    result = scope.classify("pull_request", pr_event(base, head))
    assert result["product"] == "false"
    assert result["examples"] == "true"


def test_docs_jobs_do_not_install_or_build_the_product_for_docs_only_changes():
    import tomllib

    manifest = tomllib.loads((ROOT / "tools/docs/pyproject.toml").read_text())
    assert manifest["tool"]["uv"]["package"] is False
    lock = tomllib.loads((ROOT / "tools/docs/uv.lock").read_text())
    assert not any(
        p["name"].startswith(
            ("outerspace-apizr", "apizr-oci", "apizr-attest", "apizr-mcp")
        )
        for p in lock["package"]
    )
    workflow = yaml.safe_load((ROOT / ".github/workflows/mkdocs.yaml").read_text())
    for job in ("build", "deploy"):
        for step in workflow["jobs"][job]["steps"]:
            command = step.get("run", "")
            if "uv run" in command or "uv sync" in command:
                assert "--project tools/docs --locked" in command
            if "uv build" in command:
                assert step["if"] == "needs.scope.outputs.product != 'false'"
    tooling = next(
        s
        for s in workflow["jobs"]["build"]["steps"]
        if "pytest -c tools/docs/pyproject.toml tests/test_ci_scope.py"
        in s.get("run", "")
    )
    assert "if" not in tooling
    public_examples = next(
        s
        for s in workflow["jobs"]["build"]["steps"]
        if s.get("name")
        == "Check current and historical examples with published wheels outside the checkout"
    )
    assert public_examples["if"] == "needs.scope.outputs.examples != 'false'"
    assert "outerspace-apizr[http,mcp]==0.4.5" in public_examples["run"]
    assert (
        '--example-python "$RUNNER_TEMP/docs-public/bin/python"'
        in public_examples["run"]
    )
    assert "uv build" not in public_examples["run"]
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    for step in ci["jobs"]["quality"]["steps"]:
        command = step.get("run", "")
        if "uv " in command or step.get("uses") == "./.github/actions/install-attest":
            assert step["if"] == "needs.scope.outputs.product != 'false'"


def test_docs_dependencies_keep_reviewed_sources_versions_and_archive_hashes():
    # The isolated environment reuses reviewed versions. A new dependency or
    # version must first pass the existing root source/license/security policy.
    import tomllib

    reviewed = {
        (p["name"], p["version"]): p
        for p in tomllib.loads((ROOT / "uv.lock").read_text())["package"]
    }
    locked = tomllib.loads((ROOT / "tools/docs/uv.lock").read_text())["package"]
    for package in locked:
        if package["name"] == "apizr-documentation":
            assert package["source"] == {"virtual": "."}
            continue
        original = reviewed[(package["name"], package["version"])]
        assert package["source"] == original["source"]
        assert package.get("sdist") == original.get("sdist")
        assert {(w["url"], w["hash"]) for w in package.get("wheels", [])} <= {
            (w["url"], w["hash"]) for w in original.get("wheels", [])
        }


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
    assert "Only documentation, site tooling or examples changed" in summary.read_text()
