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
