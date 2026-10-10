"""Admit explicit Run context, then use the existing repository serving pipeline."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from apizr.capabilities.model import Digest
from apizr.contracts.application import (
    MAX_RESOURCE_BYTES,
    ApplicationConfig,
    ApplicationInputs,
    ApplicationResource,
)
from apizr.contracts.delivery import LocalSource
from apizr.experiments._files import FileFailure, fingerprint_file
from apizr.experiments.exposure_model import (
    EXPOSURE_FILE,
    ExperimentExposureBinding,
    ExperimentExposureRefused,
    ExperimentExposureResult,
    exposure_bytes,
    selected_dependencies,
    validate_exposure_binding,
)
from apizr.experiments.inspection import MAX_NOTEBOOK_BYTES, inspect_experiment
from apizr.experiments.model import OutputArtifact
from apizr.experiments.store import RunRecord
from apizr.exposure import ExposurePolicy, plan_exposure
from apizr.exposure.policy import Interface
from apizr.graph import GraphPolicy, RepositoryEvidence, analyze_repository, build_graph
from apizr.repository import ScanPolicy, scan_sources
from apizr.repository.discovery import SourceInput, discover
from apizr.repository.scanner import assemble
from apizr.repository.serialization import canonical_bytes
from apizr.repository_interfaces.evidence import attach_evidence
from apizr.repository_interfaces.model import RepositoryInterface
from apizr.repository_readiness import RepositoryReadinessPolicy, assess_repository
from apizr.workspace.application_resources import capture_resources
from apizr.workspace.compiler import PreparedExposure, render_bundle
from apizr.workspace.files import absolute_path, read_regular
from apizr.workspace.operator_policy import OperatorPolicy
from apizr.workspace.source_access import open_analysis_root


@dataclass(frozen=True)
class ExperimentExposure:
    result: ExperimentExposureResult
    prepared: PreparedExposure
    bundle: Mapping[str, bytes]


def _outputs(record: RunRecord, names: tuple[str, ...]) -> tuple[OutputArtifact, ...]:
    if len(set(names)) != len(names):
        raise ExperimentExposureRefused("run_artifact_duplicate")
    inventory = {output.name: output for output in record.run.outputs}
    if any(name not in inventory for name in names):
        raise ExperimentExposureRefused("run_artifact_unknown")
    selected = tuple(inventory[name] for name in sorted(names))
    if any(output.reference is None for output in selected):
        raise ExperimentExposureRefused("run_artifact_reference_missing")
    return selected


def _resources(
    root: Path,
    outputs: tuple[OutputArtifact, ...],
    config: ApplicationConfig,
    authority: OperatorPolicy | None,
) -> dict[str, bytes]:
    for output in outputs:
        assert output.reference is not None
        try:
            digest, size = fingerprint_file(root, output.reference, MAX_RESOURCE_BYTES)
        except FileFailure as error:
            raise ExperimentExposureRefused("run_artifact_" + error.code) from None
        except OSError:
            raise ExperimentExposureRefused("run_artifact_unavailable") from None
        if digest != output.digest or (output.size is not None and size != output.size):
            raise ExperimentExposureRefused("run_artifact_changed")
    # Capture through the existing ApplicationInputs boundary. Recheck retained bytes
    # too: a replacement between fingerprint and capture must never enter the bundle.
    resources = capture_resources(root, config, authority)
    for output in outputs:
        assert output.reference is not None
        data = resources[output.reference]
        if Digest.of_bytes(data).value != output.digest or (
            output.size is not None and len(data) != output.size
        ):
            raise ExperimentExposureRefused("run_artifact_changed")
    return resources


def _notebook_evidence(
    root: Path,
    record: RunRecord,
    scan: ScanPolicy,
    graph: GraphPolicy | None,
    authority: OperatorPolicy | None,
) -> tuple[RepositoryEvidence, str]:
    from apizr.generators.notebooks import inspect_notebook_bytes

    subject = record.run.subject
    assert subject.module is not None
    raw = read_regular(root / subject.reference, MAX_NOTEBOOK_BYTES)
    analysis = inspect_notebook_bytes(raw, module_name=subject.module)
    content = analysis.python_source.encode("utf-8")
    if (
        Digest.of_bytes(raw).value != subject.digest
        or Digest.of_bytes(content).value != subject.executable_digest
    ):
        raise ExperimentExposureRefused("run_source_changed")
    path = subject.module.replace(".", "/") + ".py"
    if scan.source_roots[0] != ".":
        path = scan.source_roots[0] + "/" + path
    if len(content) > scan.max_file_bytes:
        raise ExperimentExposureRefused("notebook_source_limit")
    manifest, diagnostics = discover(root, scan, operator_policy=authority)
    if any(source.path == path for source in manifest):
        raise ExperimentExposureRefused("notebook_source_collision")
    # Preserve module collisions across multiple source roots, including packages.
    existing = assemble(manifest, scan, diagnostics)
    if any(source.module == subject.module for source in existing.sources):
        raise ExperimentExposureRefused("notebook_source_collision")
    manifest.append(SourceInput(path, content, len(content)))
    if len(manifest) > scan.max_source_files:
        raise ExperimentExposureRefused("notebook_source_limit")
    catalog = scan_sources(
        (
            (source.path, source.content)
            for source in manifest
            if source.content is not None
        ),
        policy=scan,
    )
    # scan_sources enforces aggregate bounds; retain original unavailable entries
    # and discovery diagnostics as well, so the global audit remains complete.
    if not any(d.limit is not None for d in catalog.diagnostics):
        catalog = assemble(manifest, scan, diagnostics)
    paths = {source.path for source in catalog.sources if source.inspection is not None}
    sources = {
        source.path: source.content
        for source in manifest
        if source.path in paths and source.content is not None
    }
    return RepositoryEvidence(
        catalog, build_graph(catalog, sources, policy=graph), MappingProxyType(sources)
    ), path


def expose_run(
    record: RunRecord,
    root: Path,
    *,
    capability: str,
    interface: Interface,
    artifacts: tuple[str, ...] = (),
    dependencies: tuple[str, ...] = (),
    allow_conditional: bool = False,
    operator_policy: OperatorPolicy | None = None,
    scan_policy: ScanPolicy | None = None,
    graph_policy: GraphPolicy | None = None,
    readiness_policy: RepositoryReadinessPolicy | None = None,
) -> ExperimentExposure:
    """Compile in memory; no publication, execution, dependency resolution or upload."""
    record = RunRecord.model_validate(record)
    if record.run.status != "success":
        raise ExperimentExposureRefused("run_not_successful")
    policy = ExposurePolicy.model_validate(
        {
            "selection": {
                "include": (capability,),
                "include_all_ready": False,
                "exclude": (),
            },
            "interfaces": (interface,),
            "execution": {"allowed": ("direct",)},
            "eligibility": {"allow_conditional": allow_conditional},
        }
    )
    root = absolute_path(root)
    # Admission precedes inspection reads. An old Run grants no repository authority.
    os.close(open_analysis_root(root, operator_policy))
    subject = record.run.subject
    inspection = inspect_experiment(
        root / subject.reference, root=root, module_name=subject.module
    )
    current = inspection.code.source
    if (
        subject.module != current.module
        or subject.kind != current.kind
        or subject.digest != current.digest.value
        or (
            subject.kind == "notebook"
            and (
                current.transformed_digest is None
                or subject.executable_digest != current.transformed_digest.value
            )
        )
    ):
        raise ExperimentExposureRefused("run_source_changed")
    if capability not in {
        candidate.id for candidate in inspection.serving.capabilities
    }:
        raise ExperimentExposureRefused("capability_not_in_run_source")
    outputs = _outputs(record, artifacts)
    pins = selected_dependencies(record, dependencies)
    config = ApplicationConfig(
        dependencies=pins,
        resources=tuple(
            output.reference for output in outputs if output.reference is not None
        ),
    )
    resources = _resources(root, outputs, config, operator_policy)
    path = subject.reference
    if subject.kind == "python":
        evidence = analyze_repository(
            root,
            operator_policy=operator_policy,
            scan_policy=scan_policy,
            graph_policy=graph_policy,
        )
    else:
        evidence, path = _notebook_evidence(
            root, record, scan_policy or ScanPolicy(), graph_policy, operator_policy
        )
    source = next(
        (source for source in evidence.catalog.sources if source.path == path), None
    )
    expected = subject.digest if subject.kind == "python" else subject.executable_digest
    if (
        source is None
        or source.source_digest is None
        or source.source_digest.value != expected
        or source.module != subject.module
    ):
        raise ExperimentExposureRefused("run_source_changed")
    readiness = assess_repository(
        evidence.catalog,
        evidence.graph,
        policy=readiness_policy
        or RepositoryReadinessPolicy.model_validate(
            {"execution": {"modes": ("direct",)}}
        ),
    )
    plan = plan_exposure(evidence.catalog, evidence.graph, readiness, policy=policy)
    application = (
        ApplicationInputs(
            repository_digest=evidence.catalog.repository_digest,
            dependencies=pins,
            resources=tuple(
                ApplicationResource(
                    path=path, digest=Digest.of_bytes(data), size=len(data)
                )
                for path, data in sorted(resources.items())
            ),
        )
        if pins or outputs
        else None
    )
    prepared = PreparedExposure(
        evidence,
        readiness,
        policy,
        plan,
        application,
        MappingProxyType(resources),
        LocalSource(repository_digest=evidence.catalog.repository_digest),
    )
    bundle = render_bundle(prepared, interface=interface)
    contract = RepositoryInterface.model_validate_json(
        bundle["repository-interface.json"]
    )
    binding = ExperimentExposureBinding(
        run_digest=record.run_digest,
        plan_digest=record.plan_digest,
        source=subject,
        repository_digest=contract.repository_digest,
        catalog_digest=contract.catalog_digest,
        graph_digest=contract.graph_digest,
        repository_readiness_digest=contract.repository_readiness_digest,
        exposure_plan_digest=contract.exposure_plan_digest,
        repository_interface_digest=Digest.of_bytes(
            bundle["repository-interface.json"]
        ),
        capability=capability,
        interface=interface,
        outputs=outputs,
        dependencies=pins,
        application_inputs_digest=Digest.of_bytes(canonical_bytes(application))
        if application
        else None,
    )
    validate_exposure_binding(binding, record, contract, plan, application)
    bundle = attach_evidence(
        bundle, interface=interface, name=EXPOSURE_FILE, content=exposure_bytes(binding)
    )
    result = ExperimentExposureResult(
        binding=binding,
        bundle_manifest_digest=Digest.of_bytes(
            bundle[f"apizr-repository-{interface}.json"]
        ),
    )
    return ExperimentExposure(result, prepared, MappingProxyType(bundle))
