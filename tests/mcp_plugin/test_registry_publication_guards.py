"""Registry publication cannot get ahead of the protected, actually public release."""

import pytest
from mcp_distribution.metadata import candidate_artifacts, validate_metadata
from test_distribution_verifier import SHA
from test_distribution_verifier import candidate as candidate
from verify_mcp_publication import validate_release


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "dirty",
        "head",
        "source",
        "tag",
        "draft",
        "prerelease",
        "unpublished",
        "tag_target",
        "branch",
        "ancestry",
        "merge_base",
        "assets",
        "archive",
    ],
)
def test_registry_preflight_binds_all_release_identities(candidate, fault):
    descriptor = validate_metadata()
    hashes = candidate_artifacts(candidate, "0.4.5", SHA)
    release = {
        "tag_name": "v0.4.5",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-10-11T00:00:00Z",
        "assets": [
            {"name": n}
            for n in (
                "candidate.json",
                "public-comparison.json",
                "attest-verification.json",
                "release-assets.json",
            )
        ]
        + [
            {"name": n, "digest": "sha256:" + h}
            for entries in hashes.values()
            for n, h in entries.items()
        ],
    }
    tagged, branch, comparison = (
        {"sha": SHA},
        {"protected": True},
        {"status": "ahead", "merge_base_commit": {"sha": SHA}},
    )
    source, tag, head, dirty = SHA, "v0.4.5", SHA, ""
    if fault == "dirty":
        dirty = " M server.json"
    elif fault == "head":
        head = "c" * 40
    elif fault == "source":
        source = "short"
    elif fault == "tag":
        tag = "v0.4.4"
    elif fault == "draft":
        release["draft"] = True
    elif fault == "prerelease":
        release["prerelease"] = True
    elif fault == "unpublished":
        release["published_at"] = None
    elif fault == "tag_target":
        tagged["sha"] = "c" * 40
    elif fault == "branch":
        branch["protected"] = False
    elif fault == "ancestry":
        comparison["status"] = "diverged"
    elif fault == "merge_base":
        comparison["merge_base_commit"]["sha"] = "c" * 40
    elif fault == "assets":
        release["assets"].pop(0)
    elif fault == "archive":
        release["assets"][-1]["digest"] = "sha256:" + "c" * 64
    args = (
        descriptor,
        source,
        tag,
        head,
        dirty,
        release,
        tagged,
        branch,
        comparison,
        candidate,
    )
    if fault:
        with pytest.raises(ValueError):
            validate_release(*args)
    else:
        assert validate_release(*args) == hashes
