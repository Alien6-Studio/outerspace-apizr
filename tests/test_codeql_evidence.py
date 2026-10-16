"""Require exact successful native evidence without starting duplicate scans."""

import copy
import json
from datetime import datetime, timezone

import pytest

from scripts.qualification.ci import codeql_evidence as gate

NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
SOURCE = "a" * 40
REPO = "Alien6-Studio/outerspace-apizr"


def environment(ref="refs/heads/master", event="push", base=""):
    return {
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_SHA": SOURCE,
        "GITHUB_REF": ref,
        "GITHUB_EVENT_NAME": event,
        "GITHUB_BASE_REF": base,
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
        if path == "code-scanning/default-setup":
            return {"state": "configured", "languages": list(gate.LANGUAGES)}
        if not path:
            return {"default_branch": "master"}
        assert path.startswith("branches/")
        return {"protected": protected}

    monkeypatch.setattr(gate, "github", github)
    selected = gate.selection(environment(ref, event, base))
    assert selected["mode"] == expected
    assert selected["commit"] == SOURCE and selected["ref"] == ref
    assert set(selected["languages"]) == gate.LANGUAGES


@pytest.mark.parametrize(
    "setup",
    [
        {"state": "not-configured", "languages": list(gate.LANGUAGES)},
        {"state": "configured", "languages": ["python", "actions"]},
    ],
)
def test_disabled_or_partial_native_setup_fails_closed(monkeypatch, setup):
    monkeypatch.setattr(gate, "github", lambda *a, **kw: setup)
    with pytest.raises(ValueError, match="must remain enabled"):
        gate.selection(environment())


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
