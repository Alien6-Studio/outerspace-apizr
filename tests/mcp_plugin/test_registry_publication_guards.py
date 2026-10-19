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


@pytest.mark.parametrize("fault", [None, "missing", "kind", "bytes", "size"])
def test_registry_requires_the_coordinated_editor_identity(candidate, fault):
    candidate["schema"] = "apizr.release-candidate/v2"
    candidate["artifacts"].extend(
        {
            "file": f"outerspace_apizr_{plugin}-0.4.6{suffix}",
            "bytes": 1,
            "sha256": "b" * 64,
        }
        for plugin in ("oci", "attest")
        for suffix in ("-py3-none-any.whl", ".tar.gz")
    )
    for item in candidate["artifacts"]:
        item["file"] = "dist/" + item["file"]
        item["kind"] = "wheel" if item["file"].endswith(".whl") else "sdist"
    editor = {
        "file": "editor/apizr-0.4.6.vsix",
        "bytes": 1,
        "sha256": "d" * 64,
        "kind": "vsix",
    }
    candidate["artifacts"].append(editor)
    hashes = candidate_artifacts(candidate, "0.4.6", SHA)
    release = {
        "tag_name": "v0.4.6",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-10-17T00:00:00Z",
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
        ]
        + [
            {
                "name": "apizr-0.4.6.vsix",
                "digest": "sha256:" + editor["sha256"],
                "size": 1,
            }
        ],
    }
    if fault == "missing":
        release["assets"].pop()
    elif fault == "kind":
        editor["kind"] = "wheel"
    elif fault == "bytes":
        release["assets"][-1]["digest"] = "sha256:" + "e" * 64
    elif fault == "size":
        release["assets"][-1]["size"] = 2
    args = (
        validate_metadata(),
        SHA,
        "v0.4.6",
        SHA,
        "",
        release,
        {"sha": SHA},
        {"protected": True},
        {"status": "identical", "merge_base_commit": {"sha": SHA}},
        candidate,
    )
    if fault:
        with pytest.raises(ValueError):
            validate_release(*args)
    else:
        assert validate_release(*args) == hashes


@pytest.mark.parametrize("version", ["0.4.5", "0.4.6"])
def test_registry_and_glama_preflight_require_frozen_public_text_for_new_releases(
    tmp_path, monkeypatch, version
):
    from pathlib import Path

    from scripts.qualification.packaging import verify_mcp_publication as preflight

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        preflight,
        "validate_metadata",
        lambda: {"version": version, "name": "test-namespace"},
    )
    monkeypatch.setattr(
        preflight.subprocess,
        "check_output",
        lambda args, **kw: SHA if "rev-parse" in args else "",
    )
    monkeypatch.setattr(preflight, "gh", lambda path: {})
    monkeypatch.setattr(preflight, "validate_release", lambda *args: {})
    downloads = []

    def download(args, **kwargs):
        pattern = args[args.index("--pattern") + 1]
        downloads.append(pattern)
        target = Path(args[args.index("--dir") + 1])
        target.mkdir(parents=True, exist_ok=True)
        if pattern == "candidate.json":
            (target / pattern).write_text("{}")

    monkeypatch.setattr(preflight.subprocess, "run", download)
    report = tmp_path / "report.json"
    args = [
        "--release-tag",
        "v" + version,
        "--source-sha",
        SHA,
        "--report",
        str(report),
    ]
    if version == "0.4.6":
        # Even deleting the policy cannot turn this mandatory gate into a skip.
        with pytest.raises(FileNotFoundError):
            preflight.main(args)
        assert downloads == [
            "candidate.json",
            "release-metadata.json",
            "outerspace_apizr*",
        ]
        assert not report.exists()
    else:
        assert preflight.main(args) == 0
        assert downloads == ["candidate.json"]
        assert json.loads(report.read_text())["publication_performed"] is False
