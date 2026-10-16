"""Require exact successful native evidence without starting duplicate scans."""

import copy
import json
from datetime import datetime, timezone

import pytest

from scripts.qualification.ci import codeql_evidence as gate

NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
SOURCE = "a" * 40
HEAD = "b" * 40
TREE = "c" * 40
REPO = "Alien6-Studio/outerspace-apizr"


def environment(ref="refs/heads/master", event="push", base=""):
    return {
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_SHA": SOURCE,
        "GITHUB_REF": ref,
        "GITHUB_EVENT_NAME": event,
        "GITHUB_BASE_REF": base,
        "APIZR_PR_HEAD_SHA": HEAD,
    }


@pytest.mark.parametrize(
    "ref,event,base,protected,expected",
    [
        ("refs/heads/master", "push", "", False, "native"),
        ("refs/heads/master", "schedule", "", False, "native"),
        ("refs/pull/42/merge", "pull_request", "master", False, "native"),
        ("refs/pull/42/merge", "pull_request", "protected", True, "native"),
        ("refs/heads/0.4.6", "push", "", False, "retained"),
        ("refs/heads/0.4.6", "workflow_dispatch", "", False, "retained"),
        ("refs/pull/42/merge", "pull_request", "0.4.6", False, "retained"),
        ("refs/tags/v0.4.6", "push", "", False, "retained"),
    ],
)
def test_default_and_protected_refs_reuse_native_all_other_refs_retain_scan(
    monkeypatch, ref, event, base, protected, expected
):
    def github(repository, path):
        assert repository == REPO
        if not path:
            return {"default_branch": "master"}
        if path.startswith("git/commits/"):
            return {"sha": path.rsplit("/", 1)[-1], "tree": {"sha": TREE}}
        assert path.startswith("branches/")
        return {"protected": protected}

    monkeypatch.setattr(gate, "github", github)
    selected = gate.selection(environment(ref, event, base))
    assert selected["mode"] == expected
    if event == "pull_request" and expected == "native":
        assert selected["commit"] == HEAD and selected["ref"] == "refs/pull/42/head"
        assert selected["checked_commit"] == SOURCE and selected["checked_ref"] == ref
        assert selected["source_tree"] == TREE
    else:
        assert selected["commit"] == SOURCE and selected["ref"] == ref
    assert set(selected["languages"]) == gate.LANGUAGES


@pytest.mark.parametrize(
    "fault", ["changed-base", "wrong-commit", "missing-tree", "missing-head"]
)
def test_native_head_cannot_qualify_different_merged_content(monkeypatch, fault):
    def github(repository, path):
        if not path:
            return {"default_branch": "master"}
        commit = path.rsplit("/", 1)[-1]
        return {
            "sha": "d" * 40 if fault == "wrong-commit" else commit,
            "tree": {
                "sha": ""
                if fault == "missing-tree"
                else "e" * 40
                if fault == "changed-base" and commit == HEAD
                else TREE
            },
        }

    monkeypatch.setattr(gate, "github", github)
    env = environment("refs/pull/42/merge", "pull_request", "master")
    if fault == "missing-head":
        env.pop("APIZR_PR_HEAD_SHA")
    if fault == "changed-base":
        result = gate.selection(env)
        assert result["mode"] == "retained"
        assert result["commit"] == SOURCE and result["ref"] == env["GITHUB_REF"]
    else:
        with pytest.raises(ValueError):
            gate.selection(env)


@pytest.mark.parametrize("key", ["GITHUB_REPOSITORY", "GITHUB_SHA"])
def test_invalid_identity_fails_before_any_api_request(monkeypatch, key):
    monkeypatch.setattr(gate, "github", lambda *a, **kw: pytest.fail("invalid source"))
    env = environment()
    env[key] = "invalid"
    with pytest.raises(ValueError, match="Exact GitHub"):
        gate.selection(env)


def records():
    return [
        {
            "id": i + 1,
            "category": "/language:" + language,
            "commit_sha": SOURCE,
            "ref": "refs/heads/master",
            "analysis_key": gate.NATIVE,
            "created_at": "2026-10-16T11:59:00Z",
            "error": "",
        }
        for i, language in enumerate(sorted(gate.LANGUAGES))
    ]


def selected():
    return {
        "repository": REPO,
        "commit": SOURCE,
        "ref": "refs/heads/master",
        "mode": "native",
    }


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "commit_sha",
        "ref",
        "analysis_key",
        "category",
        "missing",
        "latest-failed",
        "stale",
        "future",
    ],
)
def test_native_evidence_cannot_hide_wrong_source_or_latest_failure(fault):
    data = records()
    if fault in {"commit_sha", "ref", "analysis_key", "category"}:
        data[0][fault] = "wrong"
    elif fault == "missing":
        data.pop()
    elif fault == "latest-failed":
        latest = copy.deepcopy(data[0])
        latest.update(id=100, error="analysis failed")
        data.append(latest)
    elif fault in {"stale", "future"}:
        data[0]["created_at"] = (
            "2026-10-01T12:00:00Z" if fault == "stale" else "2026-10-17T12:00:00Z"
        )
    if fault in {"latest-failed", "stale", "future"}:
        with pytest.raises(ValueError):
            gate.native_records(data, selected(), NOW)
    else:
        result = gate.native_records(data, selected(), NOW)
        assert (result is not None) is (fault is None)


@pytest.mark.parametrize("fault", [None, "missing", "source", "execution", "no-runs"])
def test_retained_sarif_binds_source_and_success(monkeypatch, tmp_path, fault):
    def github(repository, path, *, pages=False, sarif=False):
        if pages:
            current = records() if fault != "missing" else []
            for item in current:
                item["created_at"] = datetime.now(timezone.utc).isoformat()
            return [current]
        assert sarif and path.startswith("code-scanning/analyses/")
        return {
            "runs": []
            if fault == "no-runs"
            else [
                {
                    "versionControlProvenance": [
                        {"revisionId": "b" * 40 if fault == "source" else SOURCE}
                    ],
                    "invocations": [{"executionSuccessful": fault != "execution"}],
                }
            ]
        }

    monkeypatch.setattr(gate, "github", github)
    if fault:
        with pytest.raises(ValueError):
            gate.retain_native(selected(), tmp_path, 0)
        assert not (tmp_path / "native-evidence.json").exists()
    else:
        result = gate.retain_native(selected(), tmp_path, 0)
        assert result["duplicate_analysis_started"] is False
        assert len(list(tmp_path.glob("*.sarif"))) == 3
        assert (
            json.loads((tmp_path / "native-evidence.json").read_text())["result"]
            == "pass"
        )


def test_github_repository_endpoint_has_no_trailing_slash(monkeypatch):
    commands = []
    monkeypatch.setattr(
        gate.subprocess,
        "check_output",
        lambda args, **kw: commands.append(args) or "{}",
    )
    gate.github(REPO, "")
    assert commands == [["gh", "api", "repos/" + REPO]]


def test_selection_survives_codeql_recreating_its_output_directory():
    from pathlib import Path

    import yaml

    workflow = yaml.safe_load(
        (
            Path(__file__).resolve().parents[1] / ".github/workflows/security.yml"
        ).read_text()
    )
    steps = workflow["jobs"]["codeql"]["steps"]
    selection = next(s for s in steps if s.get("id") == "source")
    analyze = next(s for s in steps if "codeql-action/analyze@" in s.get("uses", ""))
    assert "--output codeql-selection " in selection["run"]
    assert analyze["with"]["output"] == "codeql-results"
    upload = next(s for s in steps if "upload-artifact@" in s.get("uses", ""))
    assert upload["with"]["path"].splitlines() == [
        "codeql-selection/",
        "codeql-results/",
    ]
