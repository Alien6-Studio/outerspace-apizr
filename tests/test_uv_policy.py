"""The upstream guard detects new series and drift without importing Apizr."""

import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = runpy.run_path(str(ROOT / "scripts/check_uv_policy.py"))["check"]


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
