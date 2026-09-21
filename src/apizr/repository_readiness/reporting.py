"""Human-readable presentation separate from canonical report bytes."""

from apizr.readiness import State

from .model import RepositoryReadinessReport


def text_report(report: RepositoryReadinessReport, *, details: bool = True) -> str:
    report = RepositoryReadinessReport.model_validate(report.model_dump(mode="json"))
    lines = [
        "Apizr repository readiness",
        "Sufficient static evidence under the supplied policy is not a runtime guarantee.",
        f"Policy: {report.policy.schema_version} (sha256:{report.policy_digest.value})",
        "Execution availability: not assessed",
        f"Catalog exit code: {report.catalog_exit_code}; graph complete: {str(report.graph_complete).lower()}",
        *(f"{state.value}: {count}" for state, count in report.counts.items()),
    ]
    lines.extend(
        ["", "Execution contract compatibility (static; not a recommendation)"]
    )
    ready = report.counts[State.READY]
    for mode in report.execution:
        lines.append(
            f"{mode.mode}: {'compatible' if mode.compatible else 'incompatible'}; missing controls: {', '.join(mode.missing_controls) or 'none'}"
        )
        lines.append(
            f"  ready declarations satisfying this mode's control requirements: {ready if mode.compatible else 0}"
        )
        if details:
            lines.append(
                f"  supported controls: {', '.join(mode.supported_controls) or 'none'}"
            )
    assessments = report.assessments if details else report.assessments[:20]
    for assessment in assessments:
        local = assessment.local_readiness
        lines.extend(
            [
                "",
                f"{assessment.capability_id}: {assessment.state.value.upper()}",
                f"  source: {assessment.source_path!r}:{local.source.line}",
                f"  local: {local.state.value}; interface eligible: {str(local.can_generate_interface).lower()}",
                f"  in IR: {str(local.in_ir).lower()}; in Catalog: {str(assessment.in_catalog).lower()}",
                f"  relationships: {assessment.relationships.state}",
            ]
        )
        for dimension in (
            local.dimensions.binding,
            local.dimensions.execution,
            local.dimensions.inputs,
            local.dimensions.outputs,
        ):
            lines.extend(f"  {r.code.value}: {r.message}" for r in dimension.reasons)
        for reason in assessment.reasons:
            context = f" [{reason.effect}]" if reason.effect else ""
            lines.append(f"  {reason.code.value}{context}: {reason.message}")
    if len(assessments) < len(report.assessments):
        lines.append("Further declarations omitted; use --details.")
    return "\n".join(lines) + "\n"
