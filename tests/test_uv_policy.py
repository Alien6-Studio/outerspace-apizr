"""The upstream guard detects new series and drift without importing Apizr."""

import runpy
from pathlib import Path

import pytest
from qualification_scripts import implementation as qualification_script

ROOT = Path(__file__).resolve().parents[1]
CHECK = runpy.run_path(str(qualification_script("check_uv_policy")))["check"]


@pytest.mark.parametrize("latest", ["0.12.17", "0.13.0", "0.13.1"])
def test_qualified_stable_series_and_development_pins(latest):
    report = CHECK(ROOT, latest)
    assert report["qualification_pin"] == "0.13.1"
    assert report["latest_stable"] == latest
    assert report["development_ci_pins_consistent"] is True


@pytest.mark.parametrize("latest", ["0.14.0", "1.13.0", "0.13.2rc1", "private-output"])
def test_new_or_unproven_series_fail_early(latest):
    with pytest.raises(ValueError, match="stable series is not qualified"):
        CHECK(ROOT, latest)


def test_inconsistent_development_pin_fails_but_publication_is_separate(tmp_path):
    resolver = tmp_path / "src/apizr/plugins/preparation/resolver.py"
    resolver.parent.mkdir(parents=True)
    resolver.write_text(
        (ROOT / "src/apizr/plugins/preparation/resolver.py").read_text()
    )
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    text = "steps:\n  - uses: astral-sh/setup-uv@reviewed\n    with:\n      version: '0.12.0'\n"
    (workflows / "publish-pypi.yml").write_text(text)
    assert CHECK(tmp_path, "0.13.1")["development_ci_pins_consistent"] is True
    (workflows / "ci.yml").write_text(text)
    with pytest.raises(ValueError, match="differs from qualification pin"):
        CHECK(tmp_path, "0.13.1")


@pytest.mark.parametrize("latest", ["0.13.1", "0.14.0"])
def test_authenticated_adapter_tag_keeps_the_real_policy_without_another_fetch(
    tmp_path, monkeypatch, latest
):
    import sys

    from scripts.qualification.ci import check_uv_policy as checker

    report = tmp_path / "report.json"
    monkeypatch.setattr(
        sys, "argv", ["check_uv_policy", "--latest", latest, "--output", str(report)]
    )

    def no_anonymous_fetch(*args, **kwargs):
        raise AssertionError("CI must not repeat an unauthenticated GitHub request")

    monkeypatch.setattr(checker.urllib.request, "urlopen", no_anonymous_fetch)
    if latest == "0.14.0":
        with pytest.raises(ValueError, match="stable series is not qualified"):
            checker.main()
        assert not report.exists()
    else:
        checker.main()
        assert report.is_file()


def test_workflow_fetches_the_upstream_tag_with_its_scoped_token():
    import yaml

    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/plugin-preparation-qualification.yml").read_text()
    )
    step = next(
        s
        for s in workflow["jobs"]["uv-policy"]["steps"]
        if "check_uv_policy" in s.get("run", "")
    )
    assert step["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert "gh api repos/astral-sh/uv/releases/latest --jq .tag_name" in step["run"]
    assert '--latest "$qualification_uv_latest"' in step["run"]
    assert "continue-on-error" not in step
