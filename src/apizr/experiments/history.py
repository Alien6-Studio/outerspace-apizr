"""Validated local history selection and bounded intended/observed presentation."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from apizr.contracts.distribution import Digest
from apizr.contracts.json import encode
from apizr.experiments.model import ExperimentValue, Reference, SourceIdentity
from apizr.experiments.serialization import MAX_ARTIFACT_BYTES
from apizr.experiments.store import RunRecord, StoreError, records


class HistoryQuery(ExperimentValue):
    status: Literal["success", "failed", "cancelled"] | None = None
    source: Reference | None = None
    capability: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    limit: Annotated[int, Field(ge=1, le=1000)] = 20


class RunSummary(ExperimentValue):
    schema_version: Literal["apizr.experiment-run-result/v1"] = (
        "apizr.experiment-run-result/v1"
    )
    run_digest: Digest
    plan_digest: Digest
    status: Literal["success", "failed", "cancelled"]
    source: SourceIdentity
    started_at: AwareDatetime | None
    metrics: Annotated[int, Field(ge=0, le=256)]
    outputs: Annotated[int, Field(ge=0, le=256)]


class HistoryList(ExperimentValue):
    schema_version: Literal["apizr.experiment-history/v1"] = (
        "apizr.experiment-history/v1"
    )
    query: HistoryQuery
    total: Annotated[int, Field(ge=0, le=4096)]
    matched: Annotated[int, Field(ge=0, le=4096)]
    runs: Annotated[tuple[RunSummary, ...], Field(max_length=1000)]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            not len(self.runs) <= self.matched <= self.total
            or len(self.runs) > self.query.limit
        ):
            raise ValueError("history_counts_invalid")
        if len({r.run_digest for r in self.runs}) != len(self.runs):
            raise ValueError("history_duplicate_run")
        if self.runs != _ordered(self.runs):
            raise ValueError("history_order_invalid")
        return self


def summary(record: RunRecord) -> RunSummary:
    record = RunRecord.model_validate(record)
    return RunSummary(
        run_digest=record.run_digest,
        plan_digest=record.plan_digest,
        status=record.run.status,
        source=record.run.subject,
        started_at=record.run.timing.started_at if record.run.timing else None,
        metrics=len(record.run.metrics),
        outputs=len(record.run.outputs),
    )


def _ordered(runs: tuple[RunSummary, ...]) -> tuple[RunSummary, ...]:
    # Two stable sorts avoid platform-dependent timestamp() limits on old dates.
    return tuple(
        sorted(
            sorted(runs, key=lambda r: r.run_digest),
            key=lambda r: r.started_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
    )


def list_runs(path: Path, *, query: HistoryQuery | None = None) -> HistoryList:
    query = HistoryQuery() if query is None else HistoryQuery.model_validate(query)
    selected: list[RunSummary] = []
    total = 0
    for record in records(path):
        # Every record is verified BEFORE filters, even past the display limit.
        total += 1
        if (
            (query.status is not None and record.run.status != query.status)
            or (
                query.source is not None
                and record.run.subject.reference != query.source
            )
            or (
                query.capability is not None
                and record.run.subject.capability_id != query.capability
            )
        ):
            continue
        selected.append(summary(record))
    return HistoryList(
        query=query,
        total=total,
        matched=len(selected),
        runs=_ordered(tuple(selected))[: query.limit],
    )


def show_run(path: Path, run_id: str) -> RunRecord:
    if not re.fullmatch(r"[0-9a-f]{12,64}", run_id):
        raise StoreError("run_id_invalid")
    found: RunRecord | None = None
    count = 0
    for record in records(path):
        if record.run_digest.startswith(run_id):
            count += 1
            found = record
    if count > 1:
        raise StoreError("run_id_ambiguous")
    if found is None:
        raise StoreError("run_not_found")
    return found


def history_bytes(result: HistoryList | RunRecord | RunSummary) -> bytes:
    result = type(result).model_validate(result)
    # Show includes two canonical artifacts, plus a bounded envelope.
    return encode(result.model_dump(mode="json"), 2 * MAX_ARTIFACT_BYTES + 4096)


def list_text(result: HistoryList) -> str:
    result = HistoryList.model_validate(result)
    lines = [
        "RUN           STATUS     STARTED                    SOURCE  METRICS OUTPUTS"
    ]
    for run in result.runs:
        started = run.started_at.isoformat() if run.started_at else "unknown"
        lines.append(
            f"{run.run_digest[:12]}  {run.status.upper():9}  {started}  {run.source.reference}  {run.metrics} {run.outputs}"
        )
    lines.append(
        f"{len(result.runs)} shown; {result.matched} matched; {result.total} verified runs."
    )
    return "\n".join(lines) + "\n"


def summary_text(result: RunSummary) -> str:
    result = RunSummary.model_validate(result)
    return f"{result.status.upper()}\nRun: {result.run_digest}\nPlan: {result.plan_digest}\nSource: {result.source.reference}\n"


def _value(value: object) -> str:
    text = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return text if len(text) <= 160 else text[:157] + "..."


def show_text(record: RunRecord) -> str:
    record = RunRecord.model_validate(record)
    plan, run = record.plan, record.run
    lines = [summary_text(summary(record)).rstrip()]
    if run.timing is not None:
        lines.append(
            f"Timing: {run.timing.started_at} → {run.timing.ended_at}; {run.timing.duration_seconds}s"
        )
    if run.diagnostics:
        lines.append("Diagnostics: " + ", ".join(d.code for d in run.diagnostics))
    lines.extend(
        [
            "",
            "Code",
            f"  {run.subject.kind}: {run.subject.reference}; sha256:{run.subject.digest}",
        ]
    )
    if run.subject.executable_digest is not None:
        lines.append(f"  Executable sha256:{run.subject.executable_digest}")
    lines.append("Data")
    observed = {a.name: a for a in run.observed_inputs}
    for item in plan.inputs[:3]:
        actual = observed.get(item.name)
        lines.append(f"  Plan {item.name}: {item.digest or 'content unknown'}")
        lines.append(
            f"  Run: {actual.digest if actual and actual.digest else 'content unknown'}; agreement: {'yes' if actual and item.digest is not None and item.digest == actual.digest else 'not established'}"
        )
    if not plan.inputs:
        lines.append("  No selected inputs; workload reads are not traced.")
    lines.append("Parameters")
    for label, items in (
        ("Plan intended values", plan.parameters),
        ("Run final global bindings", run.effective_parameters),
    ):
        lines.append(
            f"  {label}: "
            + (
                ", ".join(
                    f"{p.name}={_value(p.model_dump(mode='json')['value'])}"
                    for p in items[:3]
                )
                or "unknown"
            )
        )
    lines.append("Randomness")
    lines.append(
        "  Plan: "
        + (
            ", ".join(
                f"{r.provider}.{r.name}={_value(r.model_dump(mode='json')['value'])} ({r.origin.value})"
                for r in plan.randomness[:3]
            )
            or "unknown"
        )
    )
    lines.append(
        "  Run: "
        + (
            ", ".join(
                f"{r.provider}.{r.name} ({r.origin.value})" for r in run.randomness[:3]
            )
            or "runtime application not directly observed"
        )
    )
    lines.append("Environment")
    lines.append(
        "  Plan specifications: "
        + (
            ", ".join(
                f"{a.reference}: {a.digest or 'unknown'}"
                for a in plan.environment.artifacts[:3]
            )
            if plan.environment and plan.environment.artifacts
            else "unknown"
        )
    )
    env = run.environment
    if env is None:
        lines.append("  Worker environment not observed.")
    else:
        lines.append(
            "  Worker: "
            + "; ".join(
                f"{key}={getattr(env, key).value if getattr(env, key) else 'unknown'}"
                for key in (
                    "python_implementation",
                    "python_version",
                    "platform",
                    "architecture",
                )
            )
        )
        lines.append(
            "  Packages: "
            + (
                ", ".join(
                    f"{p.name}={p.version or 'unknown'}" for p in env.packages[:5]
                )
                or "unknown"
            )
        )
        lines.append(
            "  Runtime specifications: "
            + (
                ", ".join(
                    f"{a.reference}: {a.digest or 'unknown'}" for a in env.artifacts[:3]
                )
                or "unknown"
            )
        )
    lines.append("Metrics")
    lines.extend(
        f"  {m.name}={_value(m.model_dump(mode='json')['value'])} (runtime)"
        for m in run.metrics[:3]
    )
    if not run.metrics:
        lines.append("  No runtime metric recorded.")
    lines.append("Outputs")
    lines.extend(
        f"  {o.reference or o.name}: {o.size} bytes; sha256:{o.digest}"
        for o in run.outputs[:3]
    )
    if not run.outputs:
        lines.append("  No runtime output recorded.")
    lines.append(
        "Bounded display; --format json contains complete intended and observed evidence."
    )
    return "\n".join(lines) + "\n"
