"""Analysis origin is owned by a live acquisition, never declared beside a path."""

import copy
import json
import os

import pytest
from analysis_authorization import analysis_policy

from apizr.cli import main
from apizr.compiler import assess_readiness
from apizr.git_source import GitSnapshot
from apizr.operator_policy import AuthorizationDenied

from .authorization import authorized_snapshot, document

pytestmark = pytest.mark.timeout(30)


def test_real_origin_and_commit_are_required(remote, tls, scratch, tmp_path):
    url, _, commit = remote
    with authorized_snapshot(url, "main", subdir="service", ca_file=tls[0]) as snapshot:
        policy = analysis_policy(snapshot)
        assert snapshot.commit == commit
        assert assess_readiness(snapshot, operator_policy=policy).assessments
        # A same-looking object, declared origin, or exported pathname is not proof of acquisition.
        for invented in (
            copy.copy(snapshot),
            GitSnapshot(url, "main", commit, "service", tmp_path),
            snapshot.root,
        ):
            with pytest.raises(AuthorizationDenied):
                assess_readiness(invented, operator_policy=policy)
        with pytest.raises(AuthorizationDenied, match="operator_policy_required"):
            assess_readiness(snapshot)
        with pytest.raises(AuthorizationDenied, match="operator_operation_denied"):
            from .authorization import policy as fetch_policy

            assess_readiness(
                snapshot,
                operator_policy=fetch_policy(
                    url, "main", subdir="service", ca_file=tls[0]
                ),
            )
        changed = policy.grants[0].target.model_copy(update={"reference": commit})
        wrong = policy.model_copy(
            update={
                "grants": (policy.grants[0].model_copy(update={"target": changed}),)
            }
        )
        with pytest.raises(AuthorizationDenied, match="operator_analysis_denied"):
            assess_readiness(snapshot, operator_policy=wrong)
        assert assess_readiness(snapshot, operator_policy=policy).assessments
    with pytest.raises(AuthorizationDenied, match="operator_source_invalid"):
        assess_readiness(snapshot, operator_policy=policy)
    assert not snapshot.root.exists() and not list(scratch.iterdir())


@pytest.mark.parametrize(
    "kind", ["fetch-only", "wrong-reference", "wrong-repository", "wrong-subdir"]
)
def test_combined_cli_checks_analysis_before_acquisition_effects(
    tmp_path, monkeypatch, capsys, kind
):
    repository = "https://example.org/repo.git"
    value = document(repository, "main", subdir="src")
    if kind != "fetch-only":
        target = {
            "kind": "git",
            "repository": repository,
            "reference": "main",
            "subdir": "src",
        }
        target[
            {
                "wrong-reference": "reference",
                "wrong-repository": "repository",
                "wrong-subdir": "subdir",
            }[kind]
        ] += "-other"
        value["grants"].append(
            {
                "adapter": "repository",
                "operation": "analyze",
                "target": target,
                "permissions": ["source.analyze"],
            }
        )
    path = tmp_path / "operator.json"
    path.write_text(json.dumps(value))

    def forbidden(*a, **k):
        pytest.fail("acquisition before source admission")

    monkeypatch.setattr("apizr.cli.commands.git_source.acquire_snapshot", forbidden)
    monkeypatch.setattr(os, "scandir", forbidden)
    assert (
        main(
            [
                "readiness",
                "--git",
                repository,
                "--ref",
                "main",
                "--subdir",
                "src",
                "--operator-policy",
                str(path),
            ]
        )
        == 2
    )
    result = capsys.readouterr()
    assert not result.out
    assert json.loads(result.err)["code"] == (
        "operator_operation_denied"
        if kind == "fetch-only"
        else "operator_analysis_denied"
    )
