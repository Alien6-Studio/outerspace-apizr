"""Consume validated exposure decisions; never select or reanalyze source."""

from collections.abc import Mapping
from typing import Literal

from apizr.contracts.application import ApplicationInputs
from apizr.exposure import ExposurePlan, ExposurePolicy, plan_digest, validate_plan
from apizr.exposure.policy import Interface
from apizr.graph import Graph
from apizr.graph.builder import validated_inputs
from apizr.interfaces.planner import invocation_contract
from apizr.repository import Catalog
from apizr.repository_readiness import RepositoryReadinessReport

from .errors import BundleRefused
from .model import BundledSource, Capability, RepositoryInterface


def plan_repository_interface(
    catalog: Catalog,
    graph: Graph,
    readiness: RepositoryReadinessReport,
    policy: ExposurePolicy,
    exposure: ExposurePlan,
    sources: Mapping[str, bytes],
    *,
    interface: Interface,
    application: ApplicationInputs | None = None,
    execution_mode: Literal["direct", "local-process", "oci-container"] = "direct",
) -> RepositoryInterface:
    if application is not None:
        application = ApplicationInputs.model_validate(application.model_dump())
        if execution_mode != "direct":
            raise BundleRefused(
                "Application inputs currently require direct service execution"
            )
    sources = dict(sources)
    catalog = validated_inputs(catalog, sources)
    validate_plan(exposure, catalog, graph, readiness, policy=policy)
    if interface not in exposure.interfaces:
        raise BundleRefused("APIZR-BUNDLE-001: target interface is not planned")
    if not exposure.capabilities:
        raise BundleRefused("APIZR-BUNDLE-002: no public capabilities")
    if any(
        execution_mode not in c.compatible_execution_modes
        for c in exposure.capabilities
    ):
        raise BundleRefused(
            f"APIZR-BUNDLE-003: {execution_mode} execution is not permitted"
        )
    units = {s.module: s for s in catalog.sources if s.inspection is not None}
    bundled: list[BundledSource] = []
    for module, unit in sorted(units.items(), key=lambda item: item[0] or ""):
        assert (
            module is not None
            and unit.source_digest is not None
            and unit.size is not None
        )
        parents = module.split(".")
        for index in range(1, len(parents)):
            parent = units.get(".".join(parents[:index]))
            if parent is not None and not parent.is_package:
                raise BundleRefused(
                    "APIZR-BUNDLE-004: contradictory Python import tree"
                )
        bundled.append(
            BundledSource(
                module=module,
                source_path=unit.path,
                bundle_path=("source/" + unit.path)
                if application is not None
                else (
                    "source/"
                    + module.replace(".", "/")
                    + ("/__init__.py" if unit.is_package else ".py")
                ),
                source_digest=unit.source_digest,
                size=unit.size,
                is_package=unit.is_package,
            )
        )
    assessments = {a.capability_id: a for a in readiness.assessments}
    capabilities: list[Capability] = []
    for module, unit in sorted(units.items(), key=lambda item: item[0] or ""):
        selected = [
            c.capability_id for c in exposure.capabilities if c.module == module
        ]
        if not selected:
            continue
        assert unit.inspection is not None and module is not None
        declarations = {c.id: c for c in unit.inspection.capability_ir.capabilities}
        for identity in sorted(selected):
            assessment = assessments[identity]
            # validate_plan above recomputes the authoritative selected proof,
            # including private execution support and module initialization.
            # Do not replace it with a second, source-local eligibility gate.
            contract = invocation_contract(
                declarations[identity],
                assessment.local_readiness,
                {
                    declaration.name: declaration.type
                    for declaration in unit.inspection.readiness.structured_types
                    if declaration.type is not None
                },
            )
            public_name = ".".join(contract.capability_id.split(":")[1:])
            capabilities.append(
                Capability(
                    capability_id=contract.capability_id,
                    public_name=public_name,
                    module=module,
                    invocation=contract,
                )
            )
    if len({c.public_name for c in capabilities}) != len(capabilities):
        raise BundleRefused("APIZR-BUNDLE-005: public name collision")
    return RepositoryInterface(
        exposure_plan_digest=plan_digest(exposure),
        repository_digest=exposure.repository_digest,
        catalog_digest=exposure.catalog_digest,
        graph_digest=exposure.graph_digest,
        repository_readiness_digest=exposure.repository_readiness_digest,
        interface=interface,
        application=application,
        sources=tuple(bundled),
        capabilities=tuple(sorted(capabilities, key=lambda c: c.capability_id)),
    )
