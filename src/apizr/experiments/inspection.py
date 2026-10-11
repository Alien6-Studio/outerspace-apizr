"""Read-only composition of static experiment producers and canonical serving evidence."""

from pathlib import Path

from pydantic import TypeAdapter

from apizr.capabilities import document_digest
from apizr.capabilities.inspection import Inspection, inspect_source
from apizr.capabilities.model import Digest
from apizr.capabilities.types import logical_module
from apizr.experiments._lexical import MAX_SOURCE_BYTES, SourceLimit, bounded_tree
from apizr.experiments._locations import trace_locations
from apizr.experiments.environment import discover_environment_specs
from apizr.experiments.inputs import (
    FingerprintPolicy,
    InputDeclaration,
    InputResult,
    discover_inputs,
    fingerprint_inputs,
    select_inputs,
)
from apizr.experiments.inspection_model import (
    CodeEvidence,
    EvidenceLocation,
    ExperimentInspection,
    RepositoryServing,
    ServingEvidence,
)
from apizr.experiments.metrics import discover_metrics
from apizr.experiments.model import Reference
from apizr.experiments.notebook_source import (
    NotebookSource,
    SourceLocation,
    code_cells,
    map_exported,
)
from apizr.experiments.outputs import discover_outputs
from apizr.experiments.parameters import discover_parameters
from apizr.experiments.randomness import discover_randomness
from apizr.graph.model import Graph
from apizr.readiness import assess, report_digest
from apizr.repository.model import CapabilityEntry, Catalog
from apizr.repository_readiness import RepositoryReadinessReport, validate_report
from apizr.repository_views.model import CapabilityFocus, ReadinessDetail, ViewQuery
from apizr.repository_views.projection import readiness_view
from apizr.workspace.files import absolute_path, read_regular

MAX_NOTEBOOK_BYTES = 16 * 1024 * 1024
_REFERENCE = TypeAdapter[str](Reference)


def _serving(inspection: Inspection, reference: str) -> ServingEvidence:
    assessments = {a.capability_id: a for a in inspection.readiness.assessments}
    return ServingEvidence(
        readiness=inspection.readiness,
        capabilities=tuple(
            CapabilityEntry(
                id=c.id,
                module=inspection.capability_ir.source.module,
                source_path=reference,
                source_digest=inspection.capability_ir.source.digest,
                ir_digest=inspection.ir_digest,
                readiness_digest=inspection.readiness_digest,
                readiness=assessments[c.id].state,
                can_generate_interface=assessments[c.id].can_generate_interface,
                execution=c.execution,
                span=c.source,
            )
            for c in inspection.capability_ir.capabilities
        ),
    )


def _locations(
    result: ExperimentInspection, source: str | bytes, notebook: NotebookSource | None
) -> tuple[EvidenceLocation, ...]:
    reference = result.code.reference
    locations: list[EvidenceLocation] = []

    def add(pointer: str, line: int, column: int, *, exported: bool = False) -> None:
        if notebook is None:
            location = SourceLocation(source=reference, line=line, column=column)
        elif exported:
            location = notebook.locate_exported(reference, line)
        else:
            location = notebook.locate(reference, line, column)
        locations.append(EvidenceLocation(evidence=pointer, location=location))

    for section, collections in (
        ("data", ("diagnostics",)),
        ("parameters", ("signals", "diagnostics")),
        ("randomness", ("diagnostics",)),
        ("metrics", ("signals",)),
        ("outputs", ("signals", "diagnostics")),
    ):
        for collection in collections:
            for index, record in enumerate(
                getattr(getattr(result, section), collection)
            ):
                if record.line is not None and record.column is not None:
                    add(f"/{section}/{collection}/{index}", record.line, record.column)
    for collection, records in (
        ("code/diagnostics", result.code.diagnostics),
        ("serving/readiness/assessments", result.serving.readiness.assessments),
        (
            "serving/readiness/structured_types",
            result.serving.readiness.structured_types,
        ),
    ):
        for index, record in enumerate(records):
            add(f"/{collection}/{index}", record.source.line, 0, exported=True)
    try:
        inputs, randomness = trace_locations(source, reference)
    except SourceLimit:
        # The same producer bounds already retain a discovery-limit diagnostic.
        return tuple(locations)
    for index, artifact in enumerate(result.data.artifacts):
        for line, column in inputs.locations.get(
            artifact.reference or artifact.uri or "", ()
        ):
            add(f"/data/artifacts/{index}", line, column)
    for index, control in enumerate(result.randomness.controls):
        for line, column in randomness.locations.get(
            (control.provider, control.name), ()
        ):
            add(f"/randomness/controls/{index}", line, column)
    return tuple(locations)


def enrich_serving(
    inspection: ExperimentInspection,
    *,
    catalog: Catalog,
    graph: Graph,
    readiness: RepositoryReadinessReport,
) -> ExperimentInspection:
    """Use already-computed, exactly bound repository evidence; never scan a root."""
    inspection = ExperimentInspection.model_validate(inspection)
    catalog = Catalog.model_validate_json(catalog.model_dump_json(), strict=True)
    graph = Graph.model_validate_json(graph.model_dump_json(), strict=True)
    readiness = validate_report(readiness, catalog, graph)
    units = [u for u in catalog.sources if u.path == inspection.code.reference]
    if len(units) != 1 or units[0].inspection is None:
        raise ValueError("inspection_repository_source_missing")
    source = units[0].inspection
    if (
        source.capability_ir.source != inspection.code.source
        or source.ir_digest != inspection.code.ir_digest
        or source.readiness_digest != inspection.code.readiness_digest
        or source.readiness != inspection.serving.readiness
    ):
        raise ValueError("inspection_repository_source_mismatch")
    views = [
        readiness_view(
            catalog,
            graph,
            readiness,
            ViewQuery(view="detail", capability_id=a.capability_id, limit=1),
        )
        for a in inspection.serving.readiness.assessments
    ]
    # A summary gives the same canonical identity when there are no callable candidates.
    identity = readiness_view(
        catalog, graph, readiness, ViewQuery(view="summary")
    ).identity
    candidates: list[CapabilityFocus] = []
    for view in views:
        assert isinstance(view, ReadinessDetail) and isinstance(
            view.focus, CapabilityFocus
        )
        candidates.append(view.focus)
    serving = inspection.serving.model_copy(
        update={
            "repository": RepositoryServing(
                identity=identity, candidates=tuple(candidates)
            )
        }
    )
    return ExperimentInspection.model_validate(
        inspection.model_copy(update={"serving": serving})
    )


def inspect_experiment(
    path: str | Path,
    *,
    root: str | Path | None = None,
    module_name: str | None = None,
    declarations: tuple[InputDeclaration, ...] = (),
    fingerprint_policy: FingerprintPolicy | None = None,
) -> ExperimentInspection:
    """Inspect one explicit source, bounded local inputs and root-level environment specs.

    Relative input references are relative to root (the source parent by default).
    No imported project, framework, source execution, output reads or runtime facts.
    """
    source_path = absolute_path(Path(path))
    selected_root = source_path.parent if root is None else absolute_path(Path(root))
    if source_path.suffix not in (".py", ".ipynb"):
        raise ValueError("inspection_source_kind_invalid")
    try:
        reference = _REFERENCE.validate_python(
            source_path.relative_to(selected_root).as_posix(), strict=True
        )
        module = logical_module(
            source_path.stem if module_name is None else module_name
        )
    except ValueError:
        raise ValueError("inspection_source_identity_invalid") from None
    policy = (
        FingerprintPolicy()
        if fingerprint_policy is None
        else FingerprintPolicy.model_validate(fingerprint_policy)
    )
    raw = read_regular(
        source_path,
        MAX_SOURCE_BYTES if source_path.suffix == ".py" else MAX_NOTEBOOK_BYTES,
    )
    notebook = None
    source: str | bytes = raw
    if source_path.suffix == ".ipynb":
        notebook = code_cells(raw)
        from apizr.generators.notebooks import inspect_notebook_bytes

        analysis = inspect_notebook_bytes(raw, module_name=module)
        notebook = map_exported(notebook, analysis.python_source)
        source = notebook.source
        readiness = assess(analysis.document, analysis.python_source)
        inspection = Inspection(
            capability_ir=analysis.document,
            ir_digest=document_digest(analysis.document),
            readiness=readiness,
            readiness_digest=report_digest(readiness),
        )
    else:
        bounded_tree(raw)  # Fail before canonical analysis on excessive/invalid source.
        inspection = inspect_source(raw, module_name=module)
    selected = select_inputs(
        discover_inputs(source, source_reference=reference), declarations
    )
    captured = fingerprint_inputs(selected_root, selected.artifacts, policy=policy)
    # Build only from validated producers; model_construct permits computing derived
    # states before the final strict admission, never returning an unchecked artifact.
    draft = ExperimentInspection.model_construct(
        fingerprint_policy=policy,
        code=CodeEvidence(
            reference=reference,
            source=inspection.capability_ir.source,
            ir_digest=inspection.ir_digest,
            readiness_digest=inspection.readiness_digest,
            signal_digest=Digest.of_bytes(
                source.encode("utf-8") if isinstance(source, str) else source
            ),
            diagnostics=inspection.capability_ir.diagnostics,
        ),
        data=InputResult(
            artifacts=captured.artifacts,
            diagnostics=(*selected.diagnostics, *captured.diagnostics),
        ),
        parameters=discover_parameters(source, source_reference=reference),
        randomness=discover_randomness(source, source_reference=reference),
        environment=discover_environment_specs(selected_root),
        metrics=discover_metrics(source, source_reference=reference),
        outputs=discover_outputs(source, source_reference=reference),
        serving=_serving(inspection, reference),
    )
    return ExperimentInspection.model_validate(
        draft.model_copy(
            update={
                "states": draft.derived_states(),
                "locations": _locations(draft, source, notebook),
            }
        )
    )
