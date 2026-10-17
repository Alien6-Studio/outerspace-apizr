"""Validated local history selection and bounded intended/observed presentation."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, TypeAdapter, model_validator

from apizr.contracts.distribution import Digest
from apizr.contracts.json import encode
from apizr.experiments.capture_model import (
    CallParameter,
    CaptureIdentity,
    CaptureMode,
    SourceEvidence,
)
from apizr.experiments.model import (
    ExperimentValue,
    Metric,
    Parameter,
    Reference,
    SourceIdentity,
)
from apizr.experiments.serialization import MAX_ARTIFACT_BYTES
from apizr.experiments.store import (
    Record,
    RunRecordV2,
    StoreError,
    record_source,
    records,
    validate_record,
)


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


class RunSummaryV2(ExperimentValue):
    schema_version: Literal["apizr.experiment-run-result/v2"] = (
        "apizr.experiment-run-result/v2"
    )
    run_digest: Digest
    plan_digest: Digest
    status: Literal["success", "failed", "cancelled"]
    source: SourceIdentity | SourceEvidence
    capture: CaptureIdentity
    execution_id: (
        Annotated[str, Field(min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")]
        | None
    )
    started_at: AwareDatetime | None
    metrics: Annotated[int, Field(ge=0, le=256)]
    outputs: Annotated[int, Field(ge=0, le=256)]
    parameters: Annotated[tuple[Parameter, ...], Field(max_length=256)]
    call_parameters: Annotated[tuple[CallParameter, ...], Field(max_length=256)]
    recorded_metrics: Annotated[tuple[Metric, ...], Field(max_length=256)]


Summary = RunSummary | RunSummaryV2


class HistoryListV2(ExperimentValue):
    schema_version: Literal["apizr.experiment-history/v2"] = (
        "apizr.experiment-history/v2"
    )
    query: HistoryQuery
    total: Annotated[int, Field(ge=0, le=4096)]
    matched: Annotated[int, Field(ge=0, le=4096)]
    runs: Annotated[tuple[Summary, ...], Field(max_length=1000)]

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


_HISTORY: TypeAdapter[HistoryList | HistoryListV2] = TypeAdapter(
    Annotated[HistoryList | HistoryListV2, Field(discriminator="schema_version")]
)


def read_history(data: bytes) -> HistoryList | HistoryListV2:
    """Read the explicitly versioned bounded view without changing stored evidence."""
    if len(data) > 2 * MAX_ARTIFACT_BYTES + 4096:
        raise ValueError("history_artifact_limit")
    return _HISTORY.validate_json(data)


def summary(record: Record, *, include_values: bool = False) -> Summary:
    record = validate_record(record)
    return _summary(record, include_values=include_values)


def _summary(record: Record, *, include_values: bool = False) -> Summary:
    """Project a record validated by this operation, without a second admission."""
    if isinstance(record, RunRecordV2):
        return RunSummaryV2(
            run_digest=record.run_digest,
            plan_digest=record.plan_digest,
            status=record.run.status,
            source=record.run.subject,
            capture=record.run.capture,
            execution_id=record.run.execution_id,
            started_at=record.run.timing.started_at if record.run.timing else None,
            metrics=len(record.run.metrics),
            outputs=len(record.run.outputs),
            parameters=record.run.effective_parameters,
            call_parameters=record.run.call_parameters,
            recorded_metrics=record.run.metrics,
        )
    if include_values:
        return RunSummaryV2(
            run_digest=record.run_digest,
            plan_digest=record.plan_digest,
            status=record.run.status,
            source=record.run.subject,
            capture=CaptureIdentity(
                mode=CaptureMode.CLI_RUN
                if record.plan.execution.kind == "trusted-local-process"
                else CaptureMode.UNKNOWN,
                producer="unknown",
                producer_version="unknown",
            ),
            execution_id=None,
            started_at=record.run.timing.started_at if record.run.timing else None,
            metrics=len(record.run.metrics),
            outputs=len(record.run.outputs),
            parameters=record.run.effective_parameters,
            call_parameters=(),
            recorded_metrics=record.run.metrics,
        )
    return RunSummary(
        run_digest=record.run_digest,
        plan_digest=record.plan_digest,
        status=record.run.status,
        source=record.run.subject,
        started_at=record.run.timing.started_at if record.run.timing else None,
        metrics=len(record.run.metrics),
        outputs=len(record.run.outputs),
    )


def _ordered(runs: tuple[Summary, ...]) -> tuple[Summary, ...]:
    # Two stable sorts avoid platform-dependent timestamp() limits on old dates.
    return tuple(
        sorted(
            sorted(runs, key=lambda r: r.run_digest),
            key=lambda r: r.started_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
    )


def list_runs(
    path: Path, *, query: HistoryQuery | None = None, include_values: bool = False
) -> HistoryList | HistoryListV2:
    query = HistoryQuery() if query is None else HistoryQuery.model_validate(query)
    selected: list[Summary] = []
    total = 0
    has_v2 = False
    for record in records(path):
        # Every record is verified BEFORE filters, even past the display limit.
        total += 1
        has_v2 |= isinstance(record, RunRecordV2)
        source = record_source(record)
        if (
            (query.status is not None and record.run.status != query.status)
            or (
                query.source is not None
                and (source is None or source.reference != query.source)
            )
            or (
                query.capability is not None
                and (source is None or source.capability_id != query.capability)
            )
        ):
            continue
        selected.append(_summary(record, include_values=include_values))
    if has_v2 or include_values:
        return HistoryListV2(
            query=query,
            total=total,
            matched=len(selected),
            runs=_ordered(tuple(selected))[: query.limit],
        )
    legacy = tuple(
        item for item in _ordered(tuple(selected)) if isinstance(item, RunSummary)
    )
    return HistoryList(
        query=query,
        total=total,
        matched=len(selected),
        runs=legacy[: query.limit],
    )


def show_run(path: Path, run_id: str) -> Record:
    return select_runs(path, (run_id,))[0]


def select_runs(path: Path, run_ids: tuple[str, ...]) -> tuple[Record, ...]:
    """Resolve one or two identities after one complete bounded store validation.

    Filters never suppress corruption elsewhere. No record escapes until the
    entire iterator has completed. The operation-local selection retains at most
    two records; it is not an index, cache or targeted digest-only read.
    """
    if not 1 <= len(run_ids) <= 2 or any(
        not re.fullmatch(r"[0-9a-f]{12,64}", run_id) for run_id in run_ids
    ):
        raise StoreError("run_id_invalid")
    found: list[Record | None] = [None] * len(run_ids)
    counts = [0] * len(run_ids)
    for record in records(path):
        for index, run_id in enumerate(run_ids):
            if record.run_digest.startswith(run_id):
                counts[index] += 1
                found[index] = record
    for count in counts:
        if count > 1:
            raise StoreError("run_id_ambiguous")
        if count == 0:
            raise StoreError("run_not_found")
    return tuple(record for record in found if record is not None)


def history_bytes(result: HistoryList | HistoryListV2 | Record | Summary) -> bytes:
    result = type(result).model_validate(result)
    # Show includes two canonical artifacts, plus a bounded envelope.
    return encode(result.model_dump(mode="json"), 2 * MAX_ARTIFACT_BYTES + 4096)


def list_text(result: HistoryList | HistoryListV2) -> str:
    result = type(result).model_validate(result)
    lines = [
        "RUN           STATUS     STARTED                    SOURCE  METRICS OUTPUTS"
    ]
    for run in result.runs:
        started = run.started_at.isoformat() if run.started_at else "unknown"
        if isinstance(run, RunSummaryV2):
            source = _source_reference(run.source)
            lines.append(
                f"{run.run_digest[:12]}  {run.status.upper():9}  {started}  {source}  {run.metrics} {run.outputs}"
            )
            lines.append(
                f"  {run.capture.producer} ({run.capture.mode.value}); parameters: "
                + (
                    ", ".join(
                        f"{p.name}={_value(p.model_dump(mode='json')['value'])}"
                        for p in (*run.parameters, *run.call_parameters)[:3]
                    )
                    or "unknown"
                )
            )
            lines.append(
                "  metrics: "
                + (
                    ", ".join(
                        f"{m.name}={_value(m.model_dump(mode='json')['value'])}"
                        for m in run.recorded_metrics[:3]
                    )
                    or "unknown"
                )
            )
            continue
        lines.append(
            f"{run.run_digest[:12]}  {run.status.upper():9}  {started}  {run.source.reference}  {run.metrics} {run.outputs}"
        )
    lines.append(
        f"{len(result.runs)} shown; {result.matched} matched; {result.total} verified runs."
    )
    return "\n".join(lines) + "\n"


def summary_text(result: Summary) -> str:
    result = type(result).model_validate(result)
    if isinstance(result, RunSummaryV2):
        reference = _source_reference(result.source)
        return f"{result.status.upper()}\nRun: {result.run_digest}\nPlan: {result.plan_digest}\nSource: {reference}\nCapture: {result.capture.mode.value}; producer: {result.capture.producer}\n"
    return f"{result.status.upper()}\nRun: {result.run_digest}\nPlan: {result.plan_digest}\nSource: {result.source.reference}\n"


def _source_reference(source: SourceIdentity | SourceEvidence) -> str:
    if isinstance(source, SourceIdentity):
        return source.reference
    return source.identity.reference if source.identity else "unknown"


def _value(value: object) -> str:
    text = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return text if len(text) <= 160 else text[:157] + "..."


def show_text(record: Record) -> str:
    record = validate_record(record)
    if isinstance(record, RunRecordV2):
        return _capture_text(record) + _provider_text(record)
    plan, run = record.plan, record.run
    lines = [summary_text(_summary(record)).rstrip()]
    providers = _provider_text(record)
    if providers:
        lines.append(providers.rstrip())
    mode = "cli_run" if plan.execution.kind == "trusted-local-process" else "unknown"
    lines.append(f"Capture: {mode}; producer: unknown (v1 evidence)")
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


def _capture_text(record: RunRecordV2) -> str:
    run = record.run
    lines = [
        summary_text(_summary(record)).rstrip(),
        f"Execution: {run.execution_id} (correlation id)",
    ]
    lines.append("Parameters")
    lines.extend(
        f"  {p.name}={_value(p.model_dump(mode='json')['value'])} ({p.origin.value})"
        for p in (*run.effective_parameters, *run.call_parameters)[:3]
    )
    lines.append("Data")
    lines.extend(
        f"  {p.name}: {p.reference or p.uri or 'unknown'}; sha256:{p.digest or 'unknown'}"
        for p in run.observed_inputs[:3]
    )
    lines.append(
        "Randomness: "
        + (
            ", ".join(
                f"{p.provider}.{p.name} ({p.origin.value})" for p in run.randomness[:3]
            )
            or "unknown"
        )
    )
    lines.append("Metrics")
    lines.extend(
        f"  {m.name}={_value(m.model_dump(mode='json')['value'])}"
        for m in run.metrics[:3]
    )
    lines.append("Outputs")
    lines.extend(
        f"  {p.name}: {p.reference or 'unknown'}; sha256:{p.digest}"
        for p in run.outputs[:3]
    )
    if run.diagnostics:
        lines.append("Diagnostics: " + ", ".join(d.code for d in run.diagnostics))
    lines.append(
        "Bounded display; --format json contains complete intended and observed evidence."
    )
    return "\n".join(lines) + "\n"


def _provider_text(record: Record) -> str:
    from apizr.scientific_providers.contracts.selection import read_provenance

    report = read_provenance(record.plan.execution.controls)
    if report is None:
        return ""
    return (
        "Scientific providers (recorded static recognition)\n"
        + "\n".join(
            f"  {p.choice.identity.name} {p.choice.identity.version}: {p.diagnostic or 'active'}; "
            + (", ".join(p.selected_capabilities) or "no selected capability")
            for p in report.providers
        )
        + "\n"
    )
