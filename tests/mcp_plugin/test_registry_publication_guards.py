"""Registry publication cannot get ahead of the protected, actually public release."""

import json
import re
from unittest.mock import patch

import pytest
from mcp_distribution.metadata import candidate_artifacts, validate_metadata
from test_distribution_verifier import SHA
from test_distribution_verifier import candidate as candidate
from verify_mcp_publication import validate_release


@pytest.mark.parametrize("workflow", ["publish-mcp.yml", "verify-mcp-distribution.yml"])
@pytest.mark.parametrize(
    "fault",
    [None, "source", "tag", "draft", "tag_target", "branch", "ancestry", "merge_base"],
)
def test_workflow_admits_source_before_candidate_code_can_execute(workflow, fault):
    from mcp_distribution.metadata import REPOSITORY, ROOT

    text = (ROOT / ".github/workflows" / workflow).read_text()
    assert text.index("PYADMIT") < text.index("uses: actions/checkout@")
    block = re.search(
        r"          python3 - <<'PYADMIT'\n(.*?)\n          PYADMIT", text, re.DOTALL
    )
    assert block is not None
    source = "\n".join(line[10:] for line in block[1].splitlines())
    tag = "v0.4.6"
    responses = {
        f"releases/tags/{tag}": {
            "tag_name": tag,
            "draft": fault == "draft",
            "prerelease": False,
            "published_at": "2026-10-11",
        },
        "branches/master": {"protected": fault != "branch"},
        f"commits/{tag}": {"sha": "c" * 40 if fault == "tag_target" else SHA},
        f"compare/{SHA}...master": {
            "status": "diverged" if fault == "ancestry" else "ahead",
            "merge_base_commit": {"sha": "c" * 40 if fault == "merge_base" else SHA},
        },
    }

    def gh(arguments, **kwargs):
        assert arguments[:2] == ["gh", "api"]
        prefix = f"repos/{REPOSITORY}/"
        assert arguments[2].startswith(prefix)
        return json.dumps(responses[arguments[2][len(prefix) :]])

    environment = {
        "RELEASE_SOURCE": "short" if fault == "source" else SHA,
        "RELEASE_TAG": "unsafe/tag" if fault == "tag" else tag,
    }
    with patch.dict("os.environ", environment), patch("subprocess.check_output", gh):
        if fault:
            with pytest.raises(ValueError):
                exec(compile(source, workflow, "exec"), {})
        else:
            exec(compile(source, workflow, "exec"), {})


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
    hashes = candidate_artifacts(candidate, "0.4.6", SHA)
    release = {
        "tag_name": "v0.4.6",
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
    source, tag, head, dirty = SHA, "v0.4.6", SHA, ""
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
