"""Bounded human report and machine envelope, outside the canonical catalog."""

import json

from .model import Catalog
from .serialization import catalog_digest


def envelope_bytes(catalog: Catalog) -> bytes:
    return (
        json.dumps(
            {
                "catalog": catalog.model_dump(mode="json"),
                "catalog_digest": catalog_digest(catalog).model_dump(mode="json"),
                "statistics": catalog.statistics.model_dump(mode="json"),
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def text_report(catalog: Catalog, *, details: bool = False) -> str:
    stats = catalog.statistics
    lines = [
        "Apizr repository scan",
        "Root: .",
        "Source roots: "
        + ", ".join(repr(root) for root in catalog.scan_policy.source_roots),
        f"Sources: {stats.sources} ({stats.inspected_sources} inspected)",
        f"Capabilities: {stats.capabilities}",
        f"Readiness assessments: {stats.assessments}",
    ]
    lines.extend(
        f"{state.value.title()}: {count}" for state, count in stats.readiness.items()
    )
    lines += [
        f"Sources with diagnostics: {stats.sources_with_diagnostics}",
        f"Repository diagnostics: {len(catalog.diagnostics)}",
        "",
    ]
    limit = len(catalog.sources) if details else 20
    for source in catalog.sources[:limit]:
        lines.append(f"{source.module or '(invalid module)'} [{source.path!r}]")
        if source.inspection:
            assessments = source.inspection.readiness.assessments
            for assessment in assessments if details else assessments[:10]:
                lines.append(
                    f"  {assessment.source.symbol}: {assessment.state.value.upper()}"
                )
            if not details and len(assessments) > 10:
                lines.append(
                    "  Further assessments omitted; use --details or --format json."
                )
            if details:
                for diagnostic in source.inspection.capability_ir.diagnostics:
                    lines.append(
                        f"  {diagnostic.code.value} line {diagnostic.source.line}: {diagnostic.message}"
                    )
                for assessment in assessments:
                    for dimension in (
                        assessment.dimensions.binding,
                        assessment.dimensions.execution,
                        assessment.dimensions.inputs,
                        assessment.dimensions.outputs,
                    ):
                        for reason in dimension.reasons:
                            lines.append(
                                f"  {reason.code.value} line {reason.line}: {reason.message}"
                            )
    if len(catalog.sources) > limit:
        lines.append("Further sources omitted; use --details or --format json.")
    for diagnostic in catalog.diagnostics if details else catalog.diagnostics[:10]:
        lines.append(
            f"{diagnostic.code.value} {diagnostic.severity.value} {diagnostic.path!r}: {diagnostic.message}"
        )
    if not details and len(catalog.diagnostics) > 10:
        lines.append("Further diagnostics omitted; use --details or --format json.")
    lines += [
        f"Repository digest: sha256:{catalog.repository_digest.value}",
        f"Catalog digest: sha256:{catalog_digest(catalog).value}",
    ]
    return "\n".join(lines) + "\n"
