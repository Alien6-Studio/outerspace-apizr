"""Consume validated exposure decisions; never select or reanalyze source."""

from collections.abc import Mapping
from typing import Literal

from apizr.exposure import ExposurePlan, ExposurePolicy, plan_digest, validate_plan
from apizr.exposure.policy import Interface
from apizr.graph import Graph
from apizr.graph.builder import validated_inputs
from apizr.interfaces.planner import plan as invocation_plan
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
    execution_mode: Literal["direct", "local-process", "oci-container"] = "direct",
) -> RepositoryInterface:
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
                bundle_path="source/"
                + module.replace(".", "/")
                + ("/__init__.py" if unit.is_package else ".py"),
                source_digest=unit.source_digest,
                size=unit.size,
                is_package=unit.is_package,
            )
        )
    capabilities: list[Capability] = []
    for module, unit in sorted(units.items(), key=lambda item: item[0] or ""):
        selected = [
            c.capability_id for c in exposure.capabilities if c.module == module
        ]
        if not selected:
            continue
        assert unit.inspection is not None and module is not None
        invocation = invocation_plan(
            unit.inspection, sources[unit.path], select=selected
        )
        for contract in invocation.capabilities:
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
        sources=tuple(bundled),
        capabilities=tuple(sorted(capabilities, key=lambda c: c.capability_id)),
    )
