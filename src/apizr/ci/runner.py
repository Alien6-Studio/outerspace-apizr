"""One static compiler path for local callers and both forge wrappers."""

import os
import stat
from pathlib import Path

from apizr.capabilities.model import Digest
from apizr.exposure import ExposurePolicy, ExposureRefused, plan_bytes, plan_digest
from apizr.interfaces.serialization import json_bytes
from apizr.onboarding.diagnostics import doctor, load_json
from apizr.repository_interfaces import BundleRefused
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_readiness import (
    RepositoryReadinessPolicy,
    report_bytes,
    report_digest,
)
from apizr.workspace.compiler import prepare_exposure, render_bundle
from apizr.workspace.files import absolute_path, directory_fd, read_regular
from apizr.workspace.operator_policy import OperatorPolicy, load_operator_policy
from apizr.workspace.project import MAX_PROJECT_BYTES, load_project

from .models import (
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACTS,
    MAX_TOTAL_BYTES,
    Artifact,
    CIResult,
    Operation,
)


class CIError(ValueError):
    """Fixed diagnostics only; never attach user input or upstream exception text."""


def fresh_output(path: Path) -> None:
    if not path.name or ".." in path.parts or "\\" in str(path):
        raise CIError("ci_output_invalid")
    path = absolute_path(path)
    with directory_fd(path.parent) as parent:
        try:
            info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not stat.S_ISDIR(info.st_mode):
            raise CIError("ci_output_invalid")
        with directory_fd(path) as target:
            if os.listdir(target):
                raise CIError("ci_output_conflict")


def analysis_authority(root: Path) -> OperatorPolicy:
    """The caller's explicit opt-in grants only analysis of this exact local root."""
    return OperatorPolicy.model_validate_json(
        json_bytes(
            {
                "schema": "apizr.operator-policy/v1",
                "grants": [
                    {
                        "adapter": "repository",
                        "operation": "analyze",
                        "target": {"kind": "local", "root": str(absolute_path(root))},
                        "permissions": ["source.analyze"],
                    }
                ],
            }
        ),
        strict=True,
    )


def execute(
    operation: Operation,
    *,
    project: Path,
    output_dir: Path,
    operator_policy: Path | None = None,
    authorize_project_analysis: bool = False,
) -> CIResult:
    if (
        operation not in ("check", "build-rest", "build-mcp")
        or type(authorize_project_analysis) is not bool
    ):
        raise CIError("ci_arguments_invalid")
    if (operator_policy is not None) == authorize_project_analysis:
        raise CIError("ci_analysis_authority_required")
    fresh_output(output_dir)
    raw = read_regular(project, MAX_PROJECT_BYTES)
    config = load_project(project)
    if read_regular(project, MAX_PROJECT_BYTES) != raw:
        raise CIError("ci_project_changed")
    root = absolute_path(config.root)
    authority = (
        load_operator_policy(operator_policy)
        if operator_policy is not None
        else analysis_authority(root)
    )
    diagnostic = "ci_complete"
    state = "success"
    checks = doctor(project=project, operator_policy=authority)
    # Keep the check outcome, without encoding the runner's Python minor version.
    checks = checks.model_copy(
        update={
            "checks": tuple(
                c.model_copy(update={"summary": "Supported Python interpreter."})
                if c.code == "python" and c.status == "pass"
                else c
                for c in checks.checks
            )
        }
    )
    artifacts = {"doctor.json": json_bytes(checks.model_dump(mode="json"))}
    readiness = None
    plan = None
    interface = None
    manifest_digest = None
    if checks.exit_code:
        state, diagnostic = "invalid", "ci_doctor_failed"
    else:
        if config.exposure_policy is None:
            raise CIError("ci_exposure_policy_required")
        policy = load_json(config.exposure_policy, ExposurePolicy)
        readiness_policy = (
            load_json(config.readiness_policy, RepositoryReadinessPolicy)
            if config.readiness_policy is not None
            else None
        )
        try:
            prepared = prepare_exposure(
                root,
                operator_policy=authority,
                policy=policy,
                application=config.application,
                scan_policy=config.scan,
                graph_policy=config.graph,
                readiness_policy=readiness_policy,
            )
            readiness, plan = prepared.readiness, prepared.plan
            if readiness.exit_code:
                state, diagnostic = "refused", "ci_readiness_refused"
            elif operation != "check":
                target = "rest" if operation == "build-rest" else "mcp"
                try:
                    bundle = render_bundle(prepared, interface=target)
                except BundleRefused:
                    state, diagnostic = "refused", "ci_bundle_refused"
                else:
                    interface = target
                    manifest_digest = Digest.of_bytes(
                        bundle[f"apizr-repository-{target}.json"]
                    )
                    artifacts.update({"bundle/" + p: b for p, b in bundle.items()})
        except ExposureRefused as error:
            readiness = error.readiness
            state, diagnostic = "refused", "ci_exposure_refused"
    if readiness is not None:
        artifacts["readiness.json"] = report_bytes(readiness)
    if plan is not None:
        artifacts["exposure-plan.json"] = plan_bytes(plan)
    if (
        len(artifacts) >= MAX_ARTIFACTS
        or any(len(b) > MAX_ARTIFACT_BYTES for b in artifacts.values())
        or sum(map(len, artifacts.values())) > MAX_TOTAL_BYTES
    ):
        raise CIError("ci_artifact_limit")
    result = CIResult.model_validate(
        {
            "operation": operation,
            "state": state,
            "diagnostic": diagnostic,
            "project_digest": Digest.of_bytes(raw),
            "repository_digest": readiness.repository_digest if readiness else None,
            "readiness_digest": report_digest(readiness) if readiness else None,
            "readiness_exit_code": readiness.exit_code if readiness else None,
            "exposure_plan_digest": plan_digest(plan) if plan else None,
            "bundle_interface": interface,
            "bundle_manifest_digest": manifest_digest,
            "artifacts": tuple(
                Artifact(path=p, digest=Digest.of_bytes(b), size=len(b))
                for p, b in sorted(artifacts.items())
            ),
        }
    )
    artifacts["result.json"] = json_bytes(result.model_dump(mode="json"))
    if sum(map(len, artifacts.values())) > MAX_TOTAL_BYTES:
        raise CIError("ci_artifact_limit")
    write_bundle(absolute_path(output_dir), artifacts)
    return result
