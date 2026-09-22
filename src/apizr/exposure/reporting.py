"""Deterministic human reports; refusals never masquerade as canonical plans."""

from apizr.graph.model import relationship_key
from apizr.readiness.model import State
from apizr.repository_readiness.model import RepositoryReadinessReport

from .model import ExposurePlan
from .planner import ExposureRefused
from .policy import ExposurePolicy

NOTICE = "An exposure plan records an explicit publication decision over static evidence; it is not an authorization grant or runtime safety proof."


def text_report(plan: ExposurePlan, readiness: RepositoryReadinessReport) -> str:
    lines = [
        "Exposure plan",
        f"Repository capabilities: {len(readiness.assessments)}",
        f"READY under policy: {readiness.counts[State.READY]}",
        f"Explicitly selected (after exclusions): {len(plan.capabilities)}",
        f"Planned: {len(plan.capabilities)}",
        "Interfaces: " + ", ".join(plan.interfaces),
        "Execution contract compatibility (runtime availability not assessed):",
    ]
    for mode in ("direct", "local-process", "oci-container"):
        lines.append(f"  {mode}: {len(plan.compatible_with(mode))}")
    lines.append("Selected capabilities:")
    for record in plan.capabilities:
        lines.append(
            f"  {record.capability_id}: {record.repository_readiness.value.upper()}; relationships {record.relationships.state}"
        )
        for reason in record.readiness_reasons:
            lines.append(f"    {reason.code.value}: {reason.message}")
        for diagnostic in record.relationships.diagnostics:
            lines.append(f"    {diagnostic.code.value}: {diagnostic.message}")
    if not plan.capabilities:
        lines.append("Warning: empty selection; nothing is planned for exposure.")
    direct = {
        relationship_key(r)
        for c in plan.capabilities
        for r in (*c.relationships.direct, *c.relationships.module_imports)
        if r.kind.value
        in {"calls_capability", "references_capability", "imports_capability"}
    }
    lines.extend(
        [
            f"Known direct capability relationships: {len(direct)} (dependencies are not automatically exposed)",
            "Observed support modules (not a complete closure): "
            + ", ".join(plan.observed_support_modules),
            "External modules observed: " + ", ".join(plan.external_modules),
            NOTICE,
        ]
    )
    return "\n".join(lines) + "\n"


def refusal_report(error: ExposureRefused, policy: ExposurePolicy) -> str:
    lines = ["Cannot create exposure plan"]
    for diagnostic in error.diagnostics:
        if diagnostic.capability_id:
            lines.append(diagnostic.capability_id)
        if diagnostic.code == "incomplete_evidence":
            lines.append("  Complete repository evidence is required.")
        elif diagnostic.code == "unknown_id":
            lines.append("  Unknown requested capability ID (include or exclude).")
        elif diagnostic.code == "ineligible":
            assert diagnostic.state is not None
            lines.append(
                f"  Repository readiness = {diagnostic.state.value.upper()}; allow_conditional = {str(policy.eligibility.allow_conditional).lower()}."
            )
        elif diagnostic.code == "interface":
            lines.append(
                f"  Shared interface contract is not eligible for {diagnostic.interface}."
            )
        else:
            lines.append("  No contract-compatible execution mode remains.")
            lines.append(
                "  Required controls: "
                + (", ".join(policy.execution.require) or "none")
            )
            lines.append("  Allowed modes: " + ", ".join(policy.execution.allowed))
    return "\n".join(lines) + "\n"
