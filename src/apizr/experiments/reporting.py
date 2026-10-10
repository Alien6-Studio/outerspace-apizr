"""Concise data-scientist presentation and deterministic, bounded inspection JSON."""

import json

from apizr.contracts.json import encode
from apizr.experiments.inspection_model import ExperimentInspection

MAX_INSPECTION_BYTES = 16 * 1024 * 1024
_SHOWN = 2


def inspection_bytes(inspection: ExperimentInspection) -> bytes:
    validated = ExperimentInspection.model_validate(inspection)
    return encode(validated.model_dump(mode="json"), MAX_INSPECTION_BYTES)


def _short(value: str, limit: int = 84) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def text_report(inspection: ExperimentInspection) -> str:
    result = ExperimentInspection.model_validate(inspection)
    lines = [
        "Experiment inspection",
        result.code.reference,
        "No code executed; runtime evidence not observed.",
        "",
    ]

    def location(pointer: str) -> str:
        matches = [
            entry.location for entry in result.locations if entry.evidence == pointer
        ]
        if not matches:
            return ""
        first = matches[0]
        return (
            f" (cell {first.cell_index}, line {first.cell_line})"
            if first.cell_index is not None
            else f" (line {first.line})"
        )

    def section(name: str, facts: list[str], fallback: str, note: str = "") -> None:
        state = getattr(result.states, name.lower()).value.upper()
        lines.append(f"{name} — {state}")
        lines.extend(f"  {fact}" for fact in facts[:_SHOWN] or [fallback])
        if len(facts) > _SHOWN:
            lines.append(f"  +{len(facts) - _SHOWN} more; see --format json")
        if note:
            lines.append(f"  {note}")

    section(
        "Code",
        [
            f"{result.code.source.kind}; module {result.code.source.module}; sha256:{result.code.source.digest.value[:12]}",
            f"{len(result.code.diagnostics)} source diagnostics",
        ]
        if result.code.diagnostics
        else [
            f"{result.code.source.kind}; module {result.code.source.module}; sha256:{result.code.source.digest.value[:12]}"
        ],
        "",
    )
    data = [
        f"{_short(a.reference or a.uri or a.name)}: "
        + (
            f"sha256:{a.digest[:12]}, {a.size} bytes"
            if a.digest is not None
            else "content unverified"
        )
        + location(f"/data/artifacts/{index}")
        for index, a in enumerate(result.data.artifacts)
    ]
    data.extend(
        d.code.replace("_", " ") + location(f"/data/diagnostics/{index}")
        for index, d in enumerate(result.data.diagnostics)
        if d.code != "remote_content_unverified"
    )
    section(
        "Data",
        data,
        "No identifiable input; dynamic references are not guessed.",
        "Dynamic input reference; value not guessed."
        if any(d.code == "dynamic_input_reference" for d in result.data.diagnostics)
        else "",
    )
    parameters = [
        f"{s.parameter.name} = {_short(json.dumps(s.parameter.model_dump(mode='json')['value'], ensure_ascii=True), 48)}"
        + location(f"/parameters/signals/{index}")
        for index, s in enumerate(result.parameters.signals)
    ]
    section(
        "Parameters",
        parameters,
        "No literal parameter candidates.",
        f"Static candidates; {len(result.parameters.diagnostics)} unresolved assignments."
        if result.parameters.diagnostics
        else "Static candidates, not runtime parameters.",
    )
    randomness = [
        f"{c.provider}.{c.name} = {_short(json.dumps(c.model_dump(mode='json')['value'], ensure_ascii=True), 48)} ({c.origin.value})"
        + location(f"/randomness/controls/{index}")
        for index, c in enumerate(result.randomness.controls)
    ]
    section(
        "Randomness",
        randomness,
        "No identifiable randomness controls.",
        "; ".join(
            sorted({d.code.replace("_", " ") for d in result.randomness.diagnostics})
        ),
    )
    environment = [
        f"{a.reference}: "
        + (f"sha256:{a.digest[:12]}" if a.digest else "content unverified")
        for a in result.environment.evidence.artifacts
    ]
    distributions = sorted(
        {
            *result.randomness.relevant_distributions,
            *result.metrics.relevant_distributions,
            *result.outputs.relevant_distributions,
        }
    )
    if distributions:
        environment.append("Source mentions: " + ", ".join(distributions))
    environment.extend(d.code.replace("_", " ") for d in result.environment.diagnostics)
    section(
        "Environment",
        environment,
        "No environment specifications detected.",
        "Experiment runtime versions not observed.",
    )
    section(
        "Metrics",
        [
            s.callable_name
            + ": value not observed"
            + location(f"/metrics/signals/{index}")
            for index, s in enumerate(result.metrics.signals)
        ],
        "No identifiable metric calls.",
    )
    outputs = [
        f"{_short(s.declaration.reference)}: output not observed"
        + location(f"/outputs/signals/{index}")
        for index, s in enumerate(result.outputs.signals)
    ]
    outputs.extend(
        d.code.replace("_", " ") + location(f"/outputs/diagnostics/{index}")
        for index, d in enumerate(result.outputs.diagnostics)
    )
    section("Outputs", outputs, "No identifiable output paths.")
    serving: list[str] = []
    repository = result.serving.repository
    for index, assessment in enumerate(result.serving.readiness.assessments):
        state = (
            assessment.state
            if repository is None
            else repository.candidates[index].selected_state
        )
        serving.append(
            f"{assessment.source.symbol}: {state.value.upper()}; {assessment.capability_id}"
            + location(f"/serving/readiness/assessments/{index}")
        )
    section(
        "Serving",
        serving,
        "No callable candidates detected.",
        "Source-local readiness; repository context not assessed."
        if repository is None
        else "Selection-scoped repository evidence; not an execution approval.",
    )
    return "\n".join(lines) + "\n"
