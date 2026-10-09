"""Typed repository orchestration shared by Python callers and the CLI.

Operations return existing contracts and propagate their existing exceptions.
They neither present results nor execute project code. Rendering is in memory;
use ``apizr.repository_interfaces.output.write_bundle`` to publish files safely.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

from apizr.capabilities.model import Digest
from apizr.contracts.application import (
    ApplicationConfig,
    ApplicationInputs,
    ApplicationResource,
)
from apizr.contracts.delivery import GitSource, LocalSource, SourceIdentity
from apizr.execution.policy import ExecutionPolicy
from apizr.exposure import ExposurePlan, ExposurePolicy, ExposureRefused, plan_exposure
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
from apizr.workspace.application_resources import capture_resources
from apizr.workspace.source_access import RepositoryInput

if TYPE_CHECKING:
    from apizr.workspace.operator_policy import OperatorPolicy


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
    application: ApplicationInputs | None = None
    resources: Mapping[str, bytes] = field(default_factory=lambda: dict[str, bytes]())
    source: SourceIdentity | None = None


def assess_readiness(
    root: RepositoryInput,
    *,
    operator_policy: "OperatorPolicy | None" = None,
    scan_policy: ScanPolicy | None = None,
    graph_policy: GraphPolicy | None = None,
    readiness_policy: RepositoryReadinessPolicy | None = None,
) -> RepositoryReadinessReport:
    """Assess one bounded discovery, without applying exposure selection.

    Report exit codes and diagnostics retain their existing meaning. Invalid
    inputs raise the underlying validation/filesystem errors; they do not exit.
    """
    artifacts = graph_repository(
        root,
        scan_policy=scan_policy,
        graph_policy=graph_policy,
        operator_policy=operator_policy,
    )
    return assess_repository(
        artifacts.catalog, artifacts.graph, policy=readiness_policy
    )


def prepare_exposure(
    root: RepositoryInput,
    *,
    operator_policy: "OperatorPolicy | None" = None,
    policy: ExposurePolicy,
    application: ApplicationConfig | None = None,
    scan_policy: ScanPolicy | None = None,
    graph_policy: GraphPolicy | None = None,
    readiness_policy: RepositoryReadinessPolicy | None = None,
) -> PreparedExposure:
    """Analyze once, assess readiness, then plan the explicit selection.

    Keep the returned context for rendering; source changes after this call do
    not replace the retained bytes. ExposureRefused propagates to the caller.
    """
    artifacts = analyze_repository(
        root,
        scan_policy=scan_policy,
        graph_policy=graph_policy,
        operator_policy=operator_policy,
    )
    readiness = assess_repository(
        artifacts.catalog, artifacts.graph, policy=readiness_policy
    )
    try:
        plan = plan_exposure(
            artifacts.catalog, artifacts.graph, readiness, policy=policy
        )
    except ExposureRefused as error:
        # Retain the already assessed evidence for callers that archive refusals;
        # do not rediscover the repository or change the planning decision.
        raise ExposureRefused(error.diagnostics, readiness=readiness) from None
    inputs = None
    resources: dict[str, bytes] = {}
    if application is not None:
        application = ApplicationConfig.model_validate(application.model_dump())
        if application.dependencies or application.resources:
            resources = capture_resources(root, application, operator_policy)
            inputs = ApplicationInputs(
                dependencies=application.dependencies,
                repository_digest=artifacts.catalog.repository_digest,
                resources=tuple(
                    ApplicationResource(
                        path=path, digest=Digest.of_bytes(data), size=len(data)
                    )
                    for path, data in sorted(resources.items())
                ),
            )
    from apizr.git_source.models import GitSnapshot

    source: SourceIdentity = LocalSource(
        repository_digest=artifacts.catalog.repository_digest
    )
    if isinstance(root, GitSnapshot):
        import os

        from apizr.git_source.acquisition import snapshot_context

        acquired, anchor = snapshot_context(root)
        os.close(anchor)
        source = GitSource(
            repository=acquired.repository,
            requested_ref=acquired.reference,
            resolved_commit=root.commit,
            subdir=acquired.subdir,
            repository_digest=artifacts.catalog.repository_digest,
        )
    return PreparedExposure(
        artifacts, readiness, policy, plan, inputs, MappingProxyType(resources), source
    )


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
        application=prepared.application,
        source_identity=prepared.source,
        resources=prepared.resources,
        execution_policy=execution_policy,
        runtime_image=runtime_image,
    )
