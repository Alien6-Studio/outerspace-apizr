"""Portable JSON evidence using existing contracts, without loading business code.

This is a projection of a direct bundle, not a new release identity. A trusted
bundle-manifest digest anchors consistency; authentication and OCI observation
remain the responsibility of the existing delivery/proof operations.
"""

import json
import os
import stat
from pathlib import Path
from typing import Literal

from apizr.capabilities.model import Digest
from apizr.contracts.delivery import BundleProvenance, identity
from apizr.contracts.results import BuildResult
from apizr.exposure import ExposurePlan, ExposurePolicy, validate_plan
from apizr.extension_runtime.protocol import unique_object
from apizr.graph import Graph
from apizr.repository import Catalog
from apizr.repository.serialization import canonical_bytes
from apizr.repository_readiness import RepositoryReadinessReport

from .model import MCPManifest, RepositoryInterface, RestManifest
from .output import write_bundle
from .runtime import validate_bundle

Interface = Literal["rest", "mcp"]
MAX_BYTES = 64 * 1024 * 1024
DOCUMENTS = {
    "repository-interface.json": RepositoryInterface,
    "capability-catalog.json": Catalog,
    "capability-graph.json": Graph,
    "repository-readiness.json": RepositoryReadinessReport,
    "exposure-policy.json": ExposurePolicy,
    "exposure-plan.json": ExposurePlan,
}


def read_document(root: Path, name: str, limit: int = MAX_BYTES) -> bytes:
    """Read one fixed-name regular file, bounded and without following links."""
    if Path(name).name != name:
        raise ValueError("Expected an evidence filename")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Expected regular evidence")
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("Evidence exceeds size limit")
        json.loads(raw, object_pairs_hook=unique_object)
        return raw
    finally:
        os.close(directory)


def verify_evidence(
    root: Path,
    *,
    interface: Interface,
    expected: Digest,
    build_result: BuildResult | None = None,
) -> RestManifest | MCPManifest:
    """Verify document schemas and links to an independently selected digest.

    Absent source/layer bytes are not verified. This does not establish publisher
    authenticity, runtime readiness, registry availability or organizational approval.
    """
    name = f"apizr-repository-{interface}.json"
    raw = read_document(root, name)
    if Digest.of_bytes(raw) != expected:
        raise ValueError("Bundle manifest digest mismatch")
    model = RestManifest if interface == "rest" else MCPManifest
    manifest = model.model_validate_json(raw)
    if canonical_bytes(manifest) != raw:
        raise ValueError("Expected canonical bundle manifest")
    names = set(DOCUMENTS) | {
        "openapi.json" if interface == "rest" else "mcp-tools.json"
    }
    if manifest.provenance_digest is not None:
        names.add("apizr-bundle-provenance.json")
    files: dict[str, bytes] = {}
    total = len(raw)
    for filename in sorted(names):
        data = read_document(root, filename, MAX_BYTES - total)
        total += len(data)
        if Digest.of_bytes(data) != manifest.artifacts.get(filename):
            raise ValueError("Evidence artifact digest mismatch")
        files[filename] = data
    contract = RepositoryInterface.model_validate_json(
        files["repository-interface.json"]
    )
    catalog = Catalog.model_validate_json(files["capability-catalog.json"])
    graph = Graph.model_validate_json(files["capability-graph.json"])
    readiness = RepositoryReadinessReport.model_validate_json(
        files["repository-readiness.json"]
    )
    policy = ExposurePolicy.model_validate_json(files["exposure-policy.json"])
    exposure = ExposurePlan.model_validate_json(files["exposure-plan.json"])
    validate_plan(exposure, catalog, graph, readiness, policy=policy)
    if (
        contract.interface != interface
        or manifest.repository_interface_digest != identity(contract)
        or contract.repository_digest != catalog.repository_digest
        or contract.catalog_digest != identity(catalog)
        or contract.graph_digest != identity(graph)
        or contract.repository_readiness_digest != identity(readiness)
        or contract.exposure_plan_digest != identity(exposure)
        or manifest.exposure_plan_digest != identity(exposure)
        or manifest.sources != contract.sources
        or manifest.application != contract.application
        or tuple(c.capability_id for c in contract.capabilities)
        != tuple(c.capability_id for c in exposure.capabilities)
    ):
        raise ValueError("Evidence binding mismatch")
    transport = (
        manifest.endpoints if isinstance(manifest, RestManifest) else manifest.tools
    )
    if len(transport) != len(contract.capabilities) or any(
        any(
            item.model_dump()[key] != value
            for key, value in capability.invocation.model_dump().items()
        )
        for item, capability in zip(transport, contract.capabilities, strict=True)
    ):
        raise ValueError("Interface binding mismatch")
    provenance = None
    if manifest.provenance_digest is not None:
        provenance = BundleProvenance.model_validate_json(
            files["apizr-bundle-provenance.json"]
        )
        if (
            identity(provenance) != manifest.provenance_digest
            or provenance.source.repository_digest != contract.repository_digest
        ):
            raise ValueError("Provenance binding mismatch")
    if build_result is not None:
        build_result = BuildResult.model_validate_json(
            build_result.model_dump_json(by_alias=True)
        )
        plan = build_result.delivery_plan
        if plan is None or (
            plan.bundle_manifest_digest != expected
            or plan.interface != interface
            or plan.catalog_digest != identity(catalog)
            or plan.graph_digest != identity(graph)
            or plan.scan_policy_digest != catalog.scan_policy_digest
            or plan.graph_policy_digest != graph.graph_policy_digest
            or plan.readiness_policy_digest != readiness.policy_digest
            or plan.repository_readiness_digest != identity(readiness)
            or plan.exposure_policy_digest != identity(policy)
            or plan.exposure_plan_digest != identity(exposure)
            or plan.repository_interface_digest != identity(contract)
            or plan.application_inputs_digest
            != (identity(contract.application) if contract.application else None)
            or (
                provenance is not None
                and (
                    plan.source != provenance.source
                    or plan.generator != provenance.generator
                )
            )
            or plan.source.repository_digest != contract.repository_digest
        ):
            raise ValueError("Build result belongs to different evidence")
    return manifest


def export_evidence(
    bundle: Path,
    output: Path,
    *,
    interface: Interface,
    build_result: BuildResult | None = None,
) -> RestManifest | MCPManifest:
    """Validate a complete direct bundle and copy only its existing JSON records."""
    document, artifacts = validate_bundle(bundle, interface)
    model = RestManifest if interface == "rest" else MCPManifest
    manifest = model.model_validate(document)
    expected = identity(manifest)
    # Typed validation and all lineage checks complete before publishing output.
    verify_evidence(
        bundle, interface=interface, expected=expected, build_result=build_result
    )
    names = set(DOCUMENTS) | {
        "openapi.json" if interface == "rest" else "mcp-tools.json"
    }
    if manifest.provenance_digest is not None:
        names.add("apizr-bundle-provenance.json")
    exported = {name: artifacts[name] for name in names}
    exported[f"apizr-repository-{interface}.json"] = canonical_bytes(manifest)
    write_bundle(output, exported)
    return manifest
