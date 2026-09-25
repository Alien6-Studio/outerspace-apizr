"""DCO enforcement must reject missing, spoofed and unsubstantiated declarations."""

import runpy
import subprocess
import sys
from pathlib import Path

import pytest

CHECK = runpy.run_path(str(Path(__file__).parents[1] / "scripts/check_dco.py"))


def commit(sha="a" * 40, message="Change\n\nSigned-off-by: Ada <ada@example.test>\n"):
    return {"sha": sha, "name": "Ada", "email": "ada@example.test", "message": message}


def test_matching_author_declaration():
    CHECK["validate"]([commit()])


@pytest.mark.parametrize(
    "message",
    [
        "No declaration",
        "Change\n\nSigned-off-by: Bob <bob@example.test>",
        "Change\n\nSigned-off-by: Ada <wrong@example.test>",
        "Signed-off-by: Ada <ada@example.test>\n\nThis is body prose, not a trailer.",
    ],
)
def test_missing_or_mismatched_declaration(message):
    with pytest.raises(ValueError, match="Missing DCO"):
        CHECK["validate"]([commit(message=message)])


def test_explicit_responsible_submitter_can_certify_a_prior_commit():
    original = commit(message="Previously submitted patch")
    remediation = commit(
        "b" * 40,
        "Review patch\n\nDCO-sign-off-for: "
        + "a" * 40
        + "\nSigned-off-by: Ada <ada@example.test>\n",
    )
    CHECK["validate"]([original, remediation])


@pytest.mark.parametrize("reference", ["a", "c" * 40, "a" * 40 + " garbage"])
def test_remediation_is_bound_to_an_exact_commit_in_the_range(reference):
    with pytest.raises(ValueError, match="references no commit"):
        CHECK["validate"](
            [
                commit(
                    message="Review\n\nDCO-sign-off-for: "
                    + reference
                    + "\nSigned-off-by: Ada <ada@example.test>\n"
                )
            ]
        )


def test_unsigned_remediation_is_not_a_declaration():
    with pytest.raises(ValueError, match="must carry"):
        CHECK["validate"]([commit(message="Review\n\nDCO-sign-off-for: " + "a" * 40)])


def test_bot_names_do_not_bypass_the_gate():
    bot = {**commit(message="Automated change"), "name": "dependabot[bot]"}
    with pytest.raises(ValueError, match="Missing DCO"):
        CHECK["validate"]([bot])


def test_grandfathering_is_an_exact_pre_adoption_commit_not_a_date_or_author():
    previous = commit(next(iter(CHECK["PRE_ADOPTION"])), "Old preparation")
    CHECK["validate"]([previous])
    with pytest.raises(ValueError, match="Missing DCO"):
        CHECK["validate"]([previous, commit(message="New unsigned change")])


def test_published_squash_repair_and_later_commits_remain_audited(tmp_path):
    """A signed correction certifies history without excusing new unsigned work."""
    script = Path(__file__).parents[1] / "scripts/check_dco.py"

    def git(*args):
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Ada",
                "-c",
                "user.email=ada@example.test",
                "-c",
                "commit.gpgsign=false",
                "-c",
                f"core.hooksPath={tmp_path / 'no-hooks'}",
                *args,
            ],
            cwd=tmp_path,
            text=True,
            timeout=10,
        ).strip()

    def audit(base):
        return subprocess.run(
            [sys.executable, str(script), "--base", base],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

    git("init")
    git("commit", "--allow-empty", "-m", "Audited baseline", "-s")
    baseline = git("rev-parse", "HEAD")
    git(
        "commit",
        "--allow-empty",
        "-m",
        "Squash\n\nSigned-off-by: alias <ada@example.test>",
    )
    squash = git("rev-parse", "HEAD")
    failed = audit(baseline)
    assert failed.returncode != 0 and squash in failed.stderr
    git(
        "commit",
        "--allow-empty",
        "-m",
        "Certify published squash\n\nDCO-sign-off-for: " + squash,
        "-s",
    )
    # The original event range cannot substantiate the historical reference.
    assert "references no commit" in audit(squash).stderr
    # Widening the range checks both declarations with the unchanged validator.
    assert audit(baseline).returncode == 0
    git("commit", "--allow-empty", "-m", "Later signed contribution", "-s")
    assert audit(baseline).returncode == 0
    git("commit", "--allow-empty", "-m", "Later unsigned contribution")
    failed = audit(baseline)
    assert failed.returncode != 0 and git("rev-parse", "HEAD") in failed.stderr
