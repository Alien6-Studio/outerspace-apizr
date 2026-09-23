"""Typed repository orchestration shared by Python callers and the CLI.

Operations return existing contracts and propagate their existing exceptions.
They neither present results nor execute project code. Rendering is in memory;
use ``apizr.repository_interfaces.output.write_bundle`` to publish files safely.
"""

from dataclasses import dataclass
from pathlib import Path

from apizr.execution.policy import ExecutionPolicy
from apizr.exposure import ExposurePlan, ExposurePolicy, plan_exposure
from apizr.exposure.policy import Interface
from apizr.graph import (
    GraphPolicy,
    RepositoryEvidence,
    analyze_repository,
    graph_repository,
)
from apizr.oci.model import ExecutionPolicyV2, RuntimeImage
from apizr.repository import ScanPolicy
from apizr.repository_readiness import (
    RepositoryReadinessPolicy,
    RepositoryReadinessReport,
    assess_repository,
)


@dataclass(frozen=True)
class PreparedExposure:
    """In-memory context, not a new serialized contract.

    Retains the exact discovery bytes with the existing evidence, independent
    readiness assessment, explicit exposure policy and canonical plan.
    """

    evidence: RepositoryEvidence
    readiness: RepositoryReadinessReport
    policy: ExposurePolicy
    plan: ExposurePlan


def assess_readiness(
    root: str | Path,
    *,
    scan_policy: ScanPolicy | None = None,
    graph_policy: GraphPolicy | None = None,
    readiness_policy: RepositoryReadinessPolicy | None = None,
) -> RepositoryReadinessReport:
    """Assess one bounded discovery, without applying exposure selection.

    Report exit codes and diagnostics retain their existing meaning. Invalid
    inputs raise the underlying validation/filesystem errors; they do not exit.
    """
    artifacts = graph_repository(
        root, scan_policy=scan_policy, graph_policy=graph_policy
    )
    return assess_repository(
        artifacts.catalog, artifacts.graph, policy=readiness_policy
    )


def prepare_exposure(
    root: str | Path,
    *,
    policy: ExposurePolicy,
    scan_policy: ScanPolicy | None = None,
    graph_policy: GraphPolicy | None = None,
    readiness_policy: RepositoryReadinessPolicy | None = None,
) -> PreparedExposure:
    """Analyze once, assess readiness, then plan the explicit selection.

    Keep the returned context for rendering; source changes after this call do
    not replace the retained bytes. ExposureRefused propagates to the caller.
    """
    artifacts = analyze_repository(
        root, scan_policy=scan_policy, graph_policy=graph_policy
    )
    readiness = assess_repository(
        artifacts.catalog, artifacts.graph, policy=readiness_policy
    )
    plan = plan_exposure(artifacts.catalog, artifacts.graph, readiness, policy=policy)
    return PreparedExposure(artifacts, readiness, policy, plan)


def render_bundle(
    prepared: PreparedExposure,
    *,
    interface: Interface,
    execution_policy: ExecutionPolicy | ExecutionPolicyV2 | None = None,
    runtime_image: RuntimeImage | None = None,
) -> dict[str, bytes]:
    """Render existing bundle artifacts without rediscovery or file writes.

    Omitted execution policy means direct; v1 selects local-process and v2 OCI.
    Existing BundleRefused, PolicyRefused and input errors propagate unchanged.
    Transport generators are loaded only here, not during analysis/planning.
    """
    from apizr.repository_interfaces.generator import render_repository_bundle

    return render_repository_bundle(
        prepared.evidence.catalog,
        prepared.evidence.graph,
        prepared.readiness,
        prepared.policy,
        prepared.plan,
        prepared.evidence.sources,
        interface=interface,
        execution_policy=execution_policy,
        runtime_image=runtime_image,
    )
