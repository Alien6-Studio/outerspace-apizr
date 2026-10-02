"""Release authorization must bind successful checks to the exact source."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "verify_release", Path(__file__).resolve().parents[1] / "scripts/verify_release.py"
)
assert spec and spec.loader
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def valid_run(branch="master"):
    return {
        "head_sha": "abc",
        "head_branch": branch,
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "path": ".github/workflows/ci.yml",
        "repository": {"full_name": release.REPOSITORY},
    }


def test_verified_source_run():
    release.validate_run(valid_run(), "abc", "ci.yml")


@pytest.mark.parametrize(
    "field,value",
    [
        ("head_sha", "other"),
        ("head_branch", "feature"),
        ("event", "pull_request"),
        ("status", "in_progress"),
        ("conclusion", "failure"),
        ("conclusion", "cancelled"),
        ("path", ".github/workflows/other.yml"),
        ("repository", {"full_name": "other/fork"}),
    ],
)
def test_release_rejects_unverified_source(field, value):
    run = valid_run()
    run[field] = value
    with pytest.raises(ValueError):
        release.validate_run(run, "abc", "ci.yml")


def test_installed_version_and_current_help(capsys):
    from importlib.metadata import version

    from apizr.app import app
    from apizr.cli import main

    assert main(["--version"]) == 0
    assert (
        capsys.readouterr().out.strip()
        == f"outerspace-apizr {version('outerspace-apizr')}"
    )
    assert app.version == version("outerspace-apizr")
    assert main(["--help"]) == 0
    text = capsys.readouterr().out
    assert text.index("capability compiler") < text.index("Legacy generation pipeline")
    assert "--notebook" in text and "--script" in text


@pytest.mark.parametrize(
    "fault,message",
    [
        (None, None),
        ("version", "final or release-candidate version"),
        ("tag", "matching immutable version tag"),
        ("sha", "Checkout must equal"),
        ("run", "successful master push run"),
        ("missing", "Missing security.yml"),
        ("newer_failed", "successful master push run"),
        ("published", "Version already exists"),
        ("pypi_error", None),
    ],
)
@pytest.mark.parametrize("release_version", ["0.3.0", "0.4.1rc1", "0.4.1"])
def test_candidate_publication_guards_without_tag_upload_or_signing(
    tmp_path, monkeypatch, capsys, fault, message, release_version
):
    import io
    import sys
    import urllib.error

    branch = release.qualification_branch(release_version)
    version = release_version + ".dev0" if fault == "version" else release_version
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname="outerspace-apizr"\nversion="{version}"\n'
    )
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "output"
    monkeypatch.setattr(
        sys, "argv", ["verify", "--run-id", "123", "--github-output", str(output)]
    )
    monkeypatch.setenv(
        "GITHUB_REF",
        "refs/heads/master" if fault == "tag" else f"refs/tags/v{release_version}",
    )
    monkeypatch.setenv("GITHUB_SHA", "wrong" if fault == "sha" else "abc")
    monkeypatch.setattr(release.subprocess, "check_output", lambda *a, **kw: "abc\n")

    def github(path):
        if path.startswith("branches/"):
            assert path == "branches/release%2F0.4.1"
            return {"protected": True}
        run = valid_run(branch)
        if path == "actions/runs/123":
            if fault == "run":
                run["head_sha"] = "wrong"
            return run
        workflow = path.split("/")[2]
        run.update(id=10, path=".github/workflows/" + workflow)
        if fault == "missing":
            return {"workflow_runs": []}
        if fault == "newer_failed":
            return {"workflow_runs": [run, {**run, "id": 11, "conclusion": "failure"}]}
        return {"workflow_runs": [run]}

    def pypi(url, **kwargs):
        assert url == f"https://pypi.org/pypi/outerspace-apizr/{release_version}/json"
        if fault == "published":
            return io.BytesIO(b"{}")
        raise urllib.error.HTTPError(
            url, 503 if fault == "pypi_error" else 404, "fixture", {}, None
        )

    monkeypatch.setattr(release, "github", github)
    monkeypatch.setattr(release.urllib.request, "urlopen", pypi)
    if fault is None:
        release.main()
        assert (
            output.read_text()
            == f"source_ref=refs/heads/{branch}\nsecurity_run_id=10\n"
        )
        assert f"Verified {release_version}, abc" in capsys.readouterr().out
    elif fault == "pypi_error":
        with pytest.raises(urllib.error.HTTPError):
            release.main()
    else:
        with pytest.raises(ValueError, match=message.replace("master", branch)):
            release.main()
    if fault:
        assert not output.exists()


def test_publication_reuses_reviewed_artifacts_and_requires_verified_receipt():
    import yaml

    root = Path(__file__).resolve().parents[1]
    workflow = yaml.load(
        (root / ".github/workflows/publish-pypi.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    jobs = workflow["jobs"]
    assert jobs["publish"]["needs"] == ["verify", "receipt"]
    assert jobs["receipt"]["needs"] == "verify"
    assert not any(
        "uv build" in step.get("run", "")
        for job in jobs.values()
        for step in job["steps"]
    )
    verify_downloads = [
        step["with"]
        for step in jobs["verify"]["steps"]
        if step.get("uses", "").startswith("actions/download-artifact@")
    ]
    for name in (
        "python-distributions",
        "distribution-checksums",
        "build-attestations",
    ):
        assert (
            next(item for item in verify_downloads if item["name"] == name)["run-id"]
            == "${{ inputs.ci_run_id }}"
        )
    assert jobs["publish"]["steps"][0]["with"]["name"] == "pending-distributions"
    staging = next(
        step for step in jobs["verify"]["steps"] if step.get("id") == "public"
    )
    assert "scripts/prepare_publication.py --dist dist" in staging["run"]
    publishers = [
        step
        for step in jobs["publish"]["steps"]
        if step.get("uses", "").startswith("pypa/")
    ]
    assert [step["with"]["packages-dir"] for step in publishers] == [
        "pending/outerspace-apizr/",
        "pending/outerspace-apizr-oci/",
        "pending/outerspace-apizr-mcp/",
        "pending/outerspace-apizr-attest/",
    ]
    assert all("skip-existing" not in step["with"] for step in publishers)
    package_input = workflow["on"]["workflow_dispatch"]["inputs"]["package"]
    assert package_input["default"] == "all"
    assert package_input["options"] == [
        "all",
        "outerspace-apizr",
        "outerspace-apizr-oci",
        "outerspace-apizr-mcp",
        "outerspace-apizr-attest",
    ]
    for publisher in publishers:
        name = publisher["with"]["packages-dir"].split("/")[1]
        assert f"inputs.package == '{name}'" in publisher["if"]
        assert "inputs.package == 'all'" in publisher["if"]
        assert "needs.verify.outputs." in publisher["if"]
    assert jobs["verify-public"]["needs"] == ["publish", "verify"]
    assert jobs["archive-evidence"]["needs"] == "verify-public"
    assert jobs["archive-evidence"]["if"] == "inputs.package == 'all'"
    provenance = next(
        step
        for step in jobs["verify"]["steps"]
        if step.get("name")
        == "Verify build provenance for all distributions and validation archive"
    )
    assert (
        "--source-digest" in provenance["run"]
        and '--source-ref "$SOURCE_REF"' in provenance["run"]
        and provenance["env"]["SOURCE_REF"] == "${{ steps.gates.outputs.source_ref }}"
    )
    receipt = next(
        step
        for step in jobs["receipt"]["steps"]
        if step.get("name") == "Sign, timestamp and verify the exact delivery"
    )
    assert "APIZR_ATTEST_SIGNING_KEY" in receipt["env"]
    assert "scripts/attest_release.py" in receipt["run"]


@pytest.mark.parametrize(
    "fault", [None, "missing", "pending", "failed", "duplicate", "version"]
)
@pytest.mark.parametrize(
    "release_version",
    ["0.4.1rc1", "0.4.1rc2", "0.4.1", "0.4.2rc1", "0.4.2rc2", "0.4.2", "0.4.3"],
)
@pytest.mark.parametrize("resume", [False, True])
def test_coordinated_release_requires_every_exact_target(
    tmp_path, monkeypatch, fault, release_version, resume
):
    import sys

    for folder in [
        tmp_path,
        *(tmp_path / "plugins" / name for name in ("oci", "attest", "mcp")),
    ]:
        folder.mkdir(parents=True, exist_ok=True)
        version = (
            "0.3.0" if fault == "version" and folder.name == "mcp" else release_version
        )
        (folder / "pyproject.toml").write_text(
            f'[project]\nname="outerspace-apizr"\nversion="{version}"\n'
        )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REF", f"refs/tags/v{release_version}")
    monkeypatch.setenv("GITHUB_SHA", "publisher-commit" if resume else "abc")
    if resume:
        monkeypatch.setenv("GITHUB_REF", f"refs/tags/v{release_version}-publish1")
    monkeypatch.setattr(
        sys,
        "argv",
        ["verify", "--run-id", "123", "--coordinated", "--source-only"]
        + (["--release-tag", f"v{release_version}"] if resume else []),
    )
    monkeypatch.setattr(release.subprocess, "check_output", lambda *a, **kw: "abc\n")
    branch = release.qualification_branch(release_version)
    names = ["distributions", "release-delivery"] + [
        f"release-target ({system}, {python})"
        for system, versions in [
            ("ubuntu-latest", ["3.11", "3.12", "3.13", "3.14"]),
            ("macos-latest", ["3.11", "3.14"]),
        ]
        for python in versions
    ]
    jobs = [{"name": name, "conclusion": "success"} for name in names]
    if fault == "missing":
        jobs.pop()
    elif fault == "pending":
        jobs[-1]["conclusion"] = None
    elif fault == "failed":
        jobs[-1]["conclusion"] = "failure"
    elif fault == "duplicate":
        jobs.append(jobs[-1])

    def github(path):
        if path.startswith("branches/"):
            return {"protected": True}
        if path == f"git/ref/tags/v{release_version}":
            return {"object": {"type": "commit", "sha": "abc"}}
        if "/jobs?" in path:
            return {"jobs": jobs}
        if path == "actions/runs/123":
            return valid_run(branch)
        workflow = path.split("/")[2]
        return {
            "workflow_runs": [
                {**valid_run(branch), "id": 10, "path": ".github/workflows/" + workflow}
            ]
        }

    monkeypatch.setattr(release, "github", github)
    if fault:
        with pytest.raises(ValueError):
            release.main()
    else:
        release.main()


@pytest.mark.parametrize("preflight", [False, True])
def test_read_only_preflight_needs_no_tag_but_still_validates_source(
    tmp_path, monkeypatch, capsys, preflight
):
    import sys

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="outerspace-apizr"\nversion="0.4.0"\n'
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_REF", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["verify", "--run-id", "123", "--source-only"]
        + (["--preflight"] if preflight else []),
    )
    monkeypatch.setattr(release.subprocess, "check_output", lambda *a, **kw: "abc\n")

    def github(path):
        if path == "actions/runs/123":
            return valid_run()
        return {
            "workflow_runs": [
                {
                    **valid_run(),
                    "id": 10,
                    "path": ".github/workflows/" + path.split("/")[2],
                }
            ]
        }

    monkeypatch.setattr(release, "github", github)
    if not preflight:
        with pytest.raises(ValueError, match="immutable version tag"):
            release.main()
    else:
        release.main()
        assert (
            "Preflight only: no tag, upload or publication authorization"
            in capsys.readouterr().out
        )
        monkeypatch.setattr(
            release, "github", lambda path: {**valid_run(), "status": "in_progress"}
        )
        with pytest.raises(ValueError, match="successful master push run"):
            release.main()


@pytest.mark.parametrize(
    "fault", [None, "version", "commit", "tree", "cycle", "annotated"]
)
def test_resumed_publication_is_bound_to_existing_remote_tag(monkeypatch, fault):
    def github(path):
        if path == "git/ref/tags/v0.4.0rc1":
            return {
                "object": {
                    "type": "tag"
                    if fault in ("annotated", "cycle")
                    else "tree"
                    if fault == "tree"
                    else "commit",
                    "sha": "wrong" if fault == "commit" else "abc",
                }
            }
        assert path == "git/tags/abc"
        return {
            "object": {"type": "tag" if fault == "cycle" else "commit", "sha": "abc"}
        }

    monkeypatch.setattr(release, "github", github)
    tag = "v0.4.0rc2" if fault == "version" else "v0.4.0rc1"
    if fault in (None, "annotated"):
        release.validate_release_tag(tag, "0.4.0rc1", "abc")
    else:
        with pytest.raises(ValueError):
            release.validate_release_tag(tag, "0.4.0rc1", "abc")


def test_resumed_workflow_keeps_source_and_publisher_separate():
    import yaml

    root = Path(__file__).resolve().parents[1]
    workflow = yaml.load(
        (root / ".github/workflows/publish-pypi.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    jobs = workflow["jobs"]
    source = next(
        step
        for step in jobs["verify"]["steps"]
        if step.get("with", {}).get("path") == "release-source"
    )
    assert source["with"]["ref"] == "${{ inputs.release_tag }}"
    gate = next(step for step in jobs["verify"]["steps"] if step.get("id") == "gates")
    assert gate["working-directory"] == "release-source"
    assert '--release-tag "$RELEASE_TAG"' in gate["run"]
    for job in ("receipt",):
        source = next(
            step
            for step in jobs[job]["steps"]
            if step.get("with", {}).get("path") == "release-source"
        )
        assert source["with"]["ref"] == "${{ needs.verify.outputs.release_sha }}"
    receipt = next(
        step
        for step in jobs["receipt"]["steps"]
        if step.get("name") == "Sign, timestamp and verify the exact delivery"
    )
    assert "--source-root release-source" in receipt["run"]
    assert '--commit "$RELEASE_SHA"' in receipt["run"]


@pytest.mark.parametrize(
    "dispatch_ref",
    [
        "refs/heads/master",
        "refs/heads/feature",
        "refs/tags/v0.4.1-publish1",
        "refs/tags/v0.4.0rc1-publish0",
    ],
)
def test_resume_refuses_unrelated_or_unprotected_dispatch(
    tmp_path, monkeypatch, dispatch_ref
):
    import sys

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="outerspace-apizr"\nversion="0.4.0rc1"\n'
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REF", dispatch_ref)
    monkeypatch.setattr(
        release.subprocess, "check_output", lambda *args, **kwargs: "abc\n"
    )
    monkeypatch.setattr(
        sys, "argv", ["verify", "--run-id", "123", "--release-tag", "v0.4.0rc1"]
    )
    monkeypatch.setattr(
        release,
        "github",
        lambda path: pytest.fail("must reject before accessing release data"),
    )
    with pytest.raises(ValueError, match="matching protected version tag"):
        release.main()


def test_public_archive_check_does_not_checkout_artifact_source():
    import yaml

    root = Path(__file__).resolve().parents[1]
    workflow = yaml.load(
        (root / ".github/workflows/publish-pypi.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    steps = workflow["jobs"]["verify-public"]["steps"]
    checkouts = [
        step for step in steps if step.get("uses", "").startswith("actions/checkout@")
    ]
    assert len(checkouts) == 1
    assert checkouts[0]["with"] == {"persist-credentials": "false"}
    public = next(
        step
        for step in steps
        if step.get("name") == "Download and compare published archives"
    )
    assert (
        public["env"]["RELEASE_VERSION"]
        == "${{ needs.verify.outputs.release_version }}"
    )
    assert '--version "$RELEASE_VERSION"' in public["run"]


@pytest.mark.parametrize("version", ["0.4.0", "0.4.0rc1"])
def test_closed_04_publications_fail_before_network(tmp_path, monkeypatch, version):
    import sys

    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname="outerspace-apizr"\nversion="{version}"\n'
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REF", f"refs/tags/v{version}")
    monkeypatch.setenv("GITHUB_SHA", "abc")
    monkeypatch.setattr(release.subprocess, "check_output", lambda *a, **kw: "abc\n")
    monkeypatch.setattr(sys, "argv", ["verify", "--run-id", "123", "--source-only"])
    monkeypatch.setattr(release, "github", lambda path: pytest.fail("no network"))
    with pytest.raises(ValueError, match="publication is closed"):
        release.main()


@pytest.mark.parametrize(
    "version", ["0.4.2rc3", "0.4.3rc1", "0.4.4", "0.5.0", "0.4.1.dev0", "0.4.1rc0"]
)
def test_future_lines_require_explicit_policy(version):
    with pytest.raises(ValueError, match="No authorized qualification branch"):
        release.qualification_branch(version)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "master",
        "feature",
        "release/0.4.2",
        "pull_request",
        "unprotected",
        "security_branch",
        "docs_branch",
        "newer_failed",
        "fork",
    ],
)
def test_041_preflight_binds_all_gates_to_protected_release_line(
    tmp_path, monkeypatch, fault
):
    import sys

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="outerspace-apizr"\nversion="0.4.1rc1"\n'
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["verify", "--run-id", "123", "--preflight", "--source-only"]
    )
    monkeypatch.setattr(release.subprocess, "check_output", lambda *a, **kw: "abc\n")

    def github(path):
        run = valid_run("release/0.4.1")
        if path.startswith("branches/"):
            assert path == "branches/release%2F0.4.1"
            return {"protected": fault != "unprotected"}
        if path == "actions/runs/123":
            if fault in {"master", "feature", "release/0.4.2"}:
                run["head_branch"] = fault
            if fault == "pull_request":
                run["event"] = fault
            if fault == "fork":
                run["repository"] = {"full_name": "other/fork"}
            return run
        workflow = path.split("/")[2]
        run.update(id=10, path=".github/workflows/" + workflow)
        if (fault, workflow) in {
            ("security_branch", "security.yml"),
            ("docs_branch", "mkdocs.yaml"),
        }:
            run["head_branch"] = "master"
        if fault == "newer_failed":
            return {"workflow_runs": [run, {**run, "id": 11, "conclusion": "failure"}]}
        return {"workflow_runs": [run]}

    monkeypatch.setattr(release, "github", github)
    if fault:
        with pytest.raises(ValueError):
            release.main()
    else:
        release.main()


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "master",
        "feature",
        "release/0.4.1",
        "release/0.4.3",
        "wrong_sha",
        "pull_request",
        "unprotected",
        "security_branch",
        "docs_branch",
        "newer_failed",
        "fork",
    ],
)
@pytest.mark.parametrize("release_version", ["0.4.2rc1", "0.4.2rc2", "0.4.2"])
def test_042_preflight_binds_all_gates_to_protected_release_line(
    tmp_path, monkeypatch, fault, release_version
):
    import sys

    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname="outerspace-apizr"\nversion="{release_version}"\n'
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["verify", "--run-id", "123", "--preflight", "--source-only"]
    )
    monkeypatch.setattr(release.subprocess, "check_output", lambda *a, **kw: "abc\n")

    def github(path):
        run = valid_run("release/0.4.2")
        if path.startswith("branches/"):
            assert path == "branches/release%2F0.4.2"
            return {"protected": fault != "unprotected"}
        if path == "actions/runs/123":
            if fault in {"master", "feature", "release/0.4.1", "release/0.4.3"}:
                run["head_branch"] = fault
            if fault == "wrong_sha":
                run["head_sha"] = "bad"
            if fault == "pull_request":
                run["event"] = fault
            if fault == "fork":
                run["repository"] = {"full_name": "other/fork"}
            return run
        workflow = path.split("/")[2]
        run.update(id=10, path=".github/workflows/" + workflow)
        if (fault, workflow) in {
            ("security_branch", "security.yml"),
            ("docs_branch", "mkdocs.yaml"),
        }:
            run["head_branch"] = "master"
        if fault == "newer_failed":
            return {"workflow_runs": [run, {**run, "id": 11, "conclusion": "failure"}]}
        return {"workflow_runs": [run]}

    monkeypatch.setattr(release, "github", github)
    if fault:
        with pytest.raises(ValueError):
            release.main()
    else:
        release.main()


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "master",
        "feature",
        "release/0.4.1",
        "release/0.4.2",
        "wrong_sha",
        "pull_request",
        "unprotected",
        "security_branch",
        "docs_branch",
        "newer_failed",
        "fork",
    ],
)
@pytest.mark.parametrize("release_version", ["0.4.3"])
def test_043_preflight_binds_all_gates_to_protected_release_line(
    tmp_path, monkeypatch, fault, release_version
):
    import sys

    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname="outerspace-apizr"\nversion="{release_version}"\n'
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["verify", "--run-id", "123", "--preflight", "--source-only"]
    )
    monkeypatch.setattr(release.subprocess, "check_output", lambda *a, **kw: "abc\n")

    def github(path):
        run = valid_run("release/0.4.3")
        if path.startswith("branches/"):
            assert path == "branches/release%2F0.4.3"
            return {"protected": fault != "unprotected"}
        if path == "actions/runs/123":
            if fault in {"master", "feature", "release/0.4.1", "release/0.4.2"}:
                run["head_branch"] = fault
            if fault == "wrong_sha":
                run["head_sha"] = "bad"
            if fault == "pull_request":
                run["event"] = fault
            if fault == "fork":
                run["repository"] = {"full_name": "other/fork"}
            return run
        workflow = path.split("/")[2]
        run.update(id=10, path=".github/workflows/" + workflow)
        if (fault, workflow) in {
            ("security_branch", "security.yml"),
            ("docs_branch", "mkdocs.yaml"),
        }:
            run["head_branch"] = "master"
        if fault == "newer_failed":
            return {"workflow_runs": [run, {**run, "id": 11, "conclusion": "failure"}]}
        return {"workflow_runs": [run]}

    monkeypatch.setattr(release, "github", github)
    if fault:
        with pytest.raises(ValueError):
            release.main()
    else:
        release.main()


def test_workflows_separate_release_validation_from_external_publication():
    import yaml

    directory = Path(__file__).resolve().parents[1] / ".github/workflows"
    workflows = {
        p.name: yaml.load(p.read_text(), Loader=yaml.BaseLoader)
        for p in directory.iterdir()
    }
    for name in ("ci.yml", "security.yml", "mkdocs.yaml"):
        triggers = workflows[name]["on"]
        assert "release/0.4.2" in triggers["push"]["branches"]
        assert "release/0.4.3" in triggers["push"]["branches"]
        assert "release/0.4.1" not in triggers["push"]["branches"]
        assert all("*" not in branch for branch in triggers["push"]["branches"])
        assert not triggers["pull_request"]  # No target-branch or path exclusions.
    docs = workflows["mkdocs.yaml"]["jobs"]
    assert (
        docs["deploy"]["if"]
        == "github.event_name == 'push' && github.ref == 'refs/heads/master'"
    )
    assert set(workflows["publish-pypi.yml"]["on"]) == {"workflow_dispatch"}
    for name in (
        "oci-service-plugin.yml",
        "attest-delivery-plugin.yml",
        "mcp-server-plugin.yml",
        "extension-packaging.yml",
        "extension-cleanup.yml",
    ):
        assert set(workflows[name]["on"]) == {"pull_request", "workflow_dispatch"}
        assert workflows[name]["permissions"] == {"contents": "read"}
    signer = workflows["ci.yml"]["jobs"]["provenance"]
    assert " ".join(signer["if"].split()) == (
        "github.event_name == 'push' && (github.ref == 'refs/heads/master' || "
        "((github.ref == 'refs/heads/release/0.4.2' || github.ref == 'refs/heads/release/0.4.3') && github.ref_protected))"
    )
    assert not any(
        step.get("uses", "").startswith("actions/checkout@") for step in signer["steps"]
    )
    for job in ("receipt", "publish"):
        environment = workflows["publish-pypi.yml"]["jobs"][job]["environment"]
        assert (
            environment if isinstance(environment, str) else environment["name"]
        ) == "pypi"


def test_current_tracked_tree_keeps_oss_product_scope():
    import subprocess

    root = Path(__file__).resolve().parents[1]
    # Encode the excluded product identifier so the assertion itself does not
    # reintroduce it into the current source tree. History is intentionally ignored.
    excluded = bytes.fromhex("7472756e78")
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    matches = [
        name.decode()
        for name in tracked.split(b"\0")
        if name and excluded in (root / name.decode()).read_bytes().lower()
    ]
    assert not matches, f"Out-of-scope product references in tracked files: {matches}"
