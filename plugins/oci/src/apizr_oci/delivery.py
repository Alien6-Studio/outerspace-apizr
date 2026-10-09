"""Compose existing validated evidence into the immutable pre-build plan."""

from pathlib import Path

from apizr.contracts.application import ApplicationInputs
from apizr.contracts.delivery import (
    PROVENANCE_FILE,
    BundleProvenance,
    DeliveryPlan,
    UnrecordedSource,
    identity,
    installed_identity,
)
from apizr.exposure.model import ExposurePlan
from apizr.graph.model import Graph
from apizr.plugins.local.models import LockedDistribution
from apizr.repository.model import Catalog
from apizr.repository_interfaces.model import (
    MCPManifest,
    RepositoryInterface,
    RestManifest,
)
from apizr.repository_interfaces.runtime import validate_bundle
from apizr.repository_readiness.model import RepositoryReadinessReport

from .model import BuildRequest


def delivery_plan(
    bundle: Path, request: BuildRequest, closure: tuple[LockedDistribution, ...]
) -> DeliveryPlan:
    document, files = validate_bundle(bundle, request.interface)
    manifest = (
        RestManifest if request.interface == "rest" else MCPManifest
    ).model_validate(document)
    contract = RepositoryInterface.model_validate_json(
        files["repository-interface.json"]
    )
    catalog = Catalog.model_validate_json(files["capability-catalog.json"])
    graph = Graph.model_validate_json(files["capability-graph.json"])
    readiness = RepositoryReadinessReport.model_validate_json(
        files["repository-readiness.json"]
    )
    exposure = ExposurePlan.model_validate_json(files["exposure-plan.json"])
    provenance = (
        BundleProvenance.model_validate_json(files[PROVENANCE_FILE])
        if manifest.provenance_digest is not None
        else None
    )
    source = (
        provenance.source
        if provenance is not None
        else UnrecordedSource(repository_digest=contract.repository_digest)
    )
    if source.repository_digest != contract.repository_digest:
        raise ValueError("Source provenance and repository disagree")
    application = (
        ApplicationInputs.model_validate(contract.application.model_dump())
        if contract.application is not None
        else None
    )
    return DeliveryPlan(
        proof_requirement=request.proof_requirement,
        source=source,
        catalog_digest=contract.catalog_digest,
        graph_digest=contract.graph_digest,
        scan_policy_digest=catalog.scan_policy_digest,
        graph_policy_digest=graph.graph_policy_digest,
        readiness_policy_digest=readiness.policy_digest,
        repository_readiness_digest=contract.repository_readiness_digest,
        exposure_policy_digest=exposure.exposure_policy_digest,
        exposure_plan_digest=contract.exposure_plan_digest,
        repository_interface_digest=manifest.repository_interface_digest,
        application_inputs_digest=identity(application)
        if application is not None
        else None,
        bundle_manifest_digest=identity(manifest),
        interface=request.interface,
        dependency_closure=closure,
        generator=provenance.generator if provenance is not None else None,
        build_tools=(
            installed_identity("outerspace-apizr"),
            installed_identity("outerspace-apizr-oci"),
        ),
        platform=request.platform,
        base_image=request.base_image,
    )
