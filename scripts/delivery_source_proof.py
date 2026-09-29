"""Acquire #189's portable application through real Git using installed core."""

import json
import shutil

from git_https_fixture import git, handler, repository
from https_fixture import certificate, https_server
from operator_policy_proof import write_git_policy


def prepare(python, repo, work, command):
    root = work / "application-git-proof"
    root.mkdir()
    cert, key = certificate(root)
    source, _ = repository(root)
    shutil.copytree(repo / "examples/application-inputs", source / "application")
    git(source, "add", "application")
    git(source, "commit", "-m", "portable application fixture")
    commit = git(source, "rev-parse", "HEAD")
    outputs = work / "application-bundles"
    outputs.mkdir()
    with https_server(cert, key, handler(root)) as url:
        origin = url + "/repo.git"
        authority = write_git_policy(
            root / "operator.json", origin, "main", subdir="application", ca_file=cert
        )
        command(
            python,
            "-I",
            "-B",
            "-c",
            """import json,sys
from pathlib import Path
from apizr.application import ApplicationConfig
from apizr.compiler import prepare_exposure,render_bundle
from apizr.exposure import ExposurePolicy
from apizr.git_source import acquire_snapshot
from apizr.operator_policy import load_operator_policy
from apizr.repository import ScanPolicy
from apizr.repository_readiness import RepositoryReadinessPolicy
from apizr.repository_interfaces.output import write_bundle
operator=load_operator_policy(Path(sys.argv[1]))
with acquire_snapshot(sys.argv[2],"main",subdir="application",ca_file=Path(sys.argv[3]),operator_policy=operator) as source:
    prepared=prepare_exposure(source,operator_policy=operator,
        scan_policy=ScanPolicy(source_roots=("src",)),
        application=ApplicationConfig(dependencies=("six==1.17.0",),resources=("data/message.txt",)),
        policy=ExposurePolicy.model_validate({"selection":{"include":["python:formatter:message"]},"interfaces":["rest","mcp"],"execution":{"allowed":["direct"]}}),
        readiness_policy=RepositoryReadinessPolicy.model_validate({"execution":{"modes":["direct"]}}))
assert not source.root.exists()
assert prepared.source.requested_ref == "main" and prepared.source.resolved_commit == sys.argv[5]
for interface in ("rest","mcp"):
    write_bundle(Path(sys.argv[4])/interface,render_bundle(prepared,interface=interface))
""",
            authority,
            origin,
            cert,
            outputs,
            commit,
        )
    provenance = json.loads((outputs / "rest/apizr-bundle-provenance.json").read_text())
    assert provenance["source"]["requested_ref"] == "main"
    assert provenance["source"]["resolved_commit"] == commit
    assert provenance["source"]["repository"] == origin
    shutil.rmtree(root)
    assert not source.exists()
    (work / "application-source-proof.json").write_text(
        json.dumps({"provenance": provenance, "source_removed": True}, indent=2)
    )
    return outputs
