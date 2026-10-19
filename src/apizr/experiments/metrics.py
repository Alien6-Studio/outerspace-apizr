"""Explicit observed metrics and source-only metric call signals."""

from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from apizr.experiments._lexical import MAX_SOURCE_BYTES as MAX_SOURCE_BYTES
from apizr.experiments.model import EvidenceOrigin, ExperimentValue, Metric, Reference


class MetricSignal(ExperimentValue):
    """One lexical occurrence, without a value or proof of execution."""

    name: Literal[
        "accuracy", "precision", "recall", "f1", "roc_auc", "mean_squared_error"
    ]
    callable_name: Literal[
        "sklearn.metrics.accuracy_score",
        "sklearn.metrics.precision_score",
        "sklearn.metrics.recall_score",
        "sklearn.metrics.f1_score",
        "sklearn.metrics.roc_auc_score",
        "sklearn.metrics.mean_squared_error",
    ]
    source: Reference
    line: Annotated[int, Field(ge=1, le=MAX_SOURCE_BYTES)]
    column: Annotated[int, Field(ge=0, le=MAX_SOURCE_BYTES)]
    origin: Literal[EvidenceOrigin.STATIC] = EvidenceOrigin.STATIC

    @model_validator(mode="after")
    def semantic_name(self) -> Self:
        if self.name != self.callable_name.rsplit(".", 1)[1].removesuffix("_score"):
            raise ValueError("metric_signal_name_mismatch")
        return self


class MetricDiagnostic(ExperimentValue):
    code: Literal["metric_source_invalid", "metric_discovery_limit"]
    source: Reference | None = None


class MetricDiscoveryResult(ExperimentValue):
    """Bounded static occurrences; not an ExperimentRun or runtime metric list."""

    signals: Annotated[tuple[MetricSignal, ...], Field(max_length=256)] = ()
    diagnostics: Annotated[tuple[MetricDiagnostic, ...], Field(max_length=512)] = ()
    relevant_distributions: Annotated[
        tuple[Literal["scikit-learn"], ...], Field(max_length=1)
    ] = ()

    @field_validator("signals")
    @classmethod
    def ordered_signals(
        cls, items: tuple[MetricSignal, ...]
    ) -> tuple[MetricSignal, ...]:
        keys = [(s.source, s.line, s.column, s.callable_name) for s in items]
        if len(keys) != len(set(keys)):
            raise ValueError("metric_signal_duplicate_occurrence")
        return tuple(
            sorted(items, key=lambda s: (s.source, s.line, s.column, s.callable_name))
        )

    @field_validator("diagnostics")
    @classmethod
    def ordered_diagnostics(
        cls, items: tuple[MetricDiagnostic, ...]
    ) -> tuple[MetricDiagnostic, ...]:
        return tuple(sorted(set(items), key=lambda d: (d.source or "", d.code)))


def capture_metric(name: str, value: object, *, unit: str | None = None) -> Metric:
    """Validate an explicitly supplied observation; no tracking state or execution."""
    try:
        return Metric.model_validate(
            {
                "name": name,
                "value": value,
                "unit": unit,
                "origin": EvidenceOrigin.RUNTIME,
            }
        )
    except (ValueError, UnicodeError):
        raise ValueError("metric_capture_invalid") from None


def discover_metrics(
    source: str | bytes, *, source_reference: str
) -> MetricDiscoveryResult:
    """Dispatch to the official built-in recognizer, installed with the core."""
    from apizr.scientific_providers.builtin.metrics import discover_metrics as recognize

    return recognize(source, source_reference=source_reference)
