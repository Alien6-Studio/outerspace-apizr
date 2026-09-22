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


def valid_run():
    return {
        "head_sha": "abc",
        "head_branch": "master",
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
        ("version", "stable release version"),
        ("tag", "matching immutable version tag"),
        ("sha", "Checkout must equal"),
        ("run", "successful master push run"),
        ("missing", "Missing security.yml"),
        ("newer_failed", "successful master push run"),
        ("published", "Version already exists"),
        ("pypi_error", None),
    ],
)
def test_candidate_publication_guards_without_tag_upload_or_signing(
    tmp_path, monkeypatch, capsys, fault, message
):
    import io
    import sys
    import urllib.error

    version = "0.3.0.dev0" if fault == "version" else "0.3.0"
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname="outerspace-apizr"\nversion="{version}"\n'
    )
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "output"
    monkeypatch.setattr(
        sys, "argv", ["verify", "--run-id", "123", "--github-output", str(output)]
    )
    monkeypatch.setenv(
        "GITHUB_REF", "refs/heads/master" if fault == "tag" else "refs/tags/v0.3.0"
    )
    monkeypatch.setenv("GITHUB_SHA", "wrong" if fault == "sha" else "abc")
    monkeypatch.setattr(release.subprocess, "check_output", lambda *a, **kw: "abc\n")

    def github(path):
        run = valid_run()
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
        assert url == "https://pypi.org/pypi/outerspace-apizr/0.3.0/json"
        if fault == "published":
            return io.BytesIO(b"{}")
        raise urllib.error.HTTPError(
            url, 503 if fault == "pypi_error" else 404, "fixture", {}, None
        )

    monkeypatch.setattr(release, "github", github)
    monkeypatch.setattr(release.urllib.request, "urlopen", pypi)
    if fault is None:
        release.main()
        assert output.read_text() == "security_run_id=10\n"
        assert "Verified 0.3.0, abc" in capsys.readouterr().out
    elif fault == "pypi_error":
        with pytest.raises(urllib.error.HTTPError):
            release.main()
    else:
        with pytest.raises(ValueError, match=message):
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
    assert jobs["publish"]["steps"][0]["with"]["name"] == "verified-distributions"
    provenance = next(
        step
        for step in jobs["verify"]["steps"]
        if step.get("name")
        == "Verify build provenance for both distributions and validation archive"
    )
    assert (
        "--source-digest" in provenance["run"]
        and "--source-ref refs/heads/master" in provenance["run"]
    )
    receipt = next(
        step
        for step in jobs["receipt"]["steps"]
        if step.get("name") == "Sign, timestamp and verify the exact delivery"
    )
    assert "APIZR_ATTEST_SIGNING_KEY" in receipt["env"]
    assert "scripts/attest_release.py" in receipt["run"]
