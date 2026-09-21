"""Human-readable presentation separate from canonical report bytes."""

from .model import RepositoryReadinessReport


def text_report(report: RepositoryReadinessReport) -> str:
    report = RepositoryReadinessReport.model_validate(report.model_dump(mode="json"))
    lines = [
        "Apizr repository readiness",
        "Sufficient static evidence under the supplied policy is not a runtime guarantee.",
        f"Policy: {report.policy.schema_version} (sha256:{report.policy_digest.value})",
        "Execution availability: not assessed",
        f"Catalog exit code: {report.catalog_exit_code}; graph complete: {str(report.graph_complete).lower()}",
        *(f"{state.value}: {count}" for state, count in report.counts.items()),
    ]
    for mode in report.execution:
        lines.append(
            f"{mode.mode}: {'compatible' if mode.compatible else 'incompatible'}; missing controls: {', '.join(mode.missing_controls) or 'none'}"
        )
    for assessment in report.assessments:
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
    return "\n".join(lines) + "\n"
