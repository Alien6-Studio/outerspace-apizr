"""Explicit observed metrics and source-only metric call signals."""

import ast
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, field_validator, model_validator

from apizr.experiments._lexical import (
    MAX_DEPTH,
    MAX_NODES,
    MAX_SOURCE_BYTES,
    LexicalVisitor,
    SourceLimit,
    bounded_tree,
)
from apizr.experiments.model import EvidenceOrigin, ExperimentValue, Metric, Reference

_CALLABLES = {
    "sklearn.metrics.accuracy_score": "accuracy",
    "sklearn.metrics.precision_score": "precision",
    "sklearn.metrics.recall_score": "recall",
    "sklearn.metrics.f1_score": "f1",
    "sklearn.metrics.roc_auc_score": "roc_auc",
    "sklearn.metrics.mean_squared_error": "mean_squared_error",
}
_MODULES = frozenset({"sklearn", "sklearn.metrics"})
_REFERENCE = TypeAdapter[str](Reference)


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
        if self.name != _CALLABLES[self.callable_name]:
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


class _Discovery(LexicalVisitor):
    def __init__(self, source: str) -> None:
        super().__init__(
            _MODULES.__contains__,
            lambda name: name in _CALLABLES or name == "sklearn.metrics",
        )
        self.source = source
        self.signals: list[MetricSignal] = []

    def visit_Call(self, node: ast.Call) -> None:
        qualified = self.resolve_call(node, max_attributes=2)
        if qualified in _CALLABLES:
            self.signals.append(
                MetricSignal.model_validate(
                    {
                        "name": _CALLABLES[qualified],
                        "callable_name": qualified,
                        "source": self.source,
                        "line": node.lineno,
                        "column": node.col_offset,
                    }
                )
            )
        self.generic_visit(node)


def discover_metrics(
    source: str | bytes, *, source_reference: str
) -> MetricDiscoveryResult:
    """Recognize six sklearn callables lexically; arguments and values stay unevaluated."""
    try:
        _REFERENCE.validate_python(source_reference, strict=True)
        tree = bounded_tree(
            source, max_bytes=MAX_SOURCE_BYTES, max_nodes=MAX_NODES, max_depth=MAX_DEPTH
        )
    except SourceLimit as error:
        return MetricDiscoveryResult(
            diagnostics=(
                MetricDiagnostic(
                    code="metric_discovery_limit",
                    source=source_reference if error.parsed else None,
                ),
            )
        )
    except (ValueError, UnicodeError, SyntaxError, RecursionError, TypeError):
        return MetricDiscoveryResult(
            diagnostics=(MetricDiagnostic(code="metric_source_invalid"),)
        )
    discovery = _Discovery(source_reference)
    discovery.visit(tree)
    if len(discovery.signals) > 256:
        return MetricDiscoveryResult(
            diagnostics=(
                MetricDiagnostic(
                    code="metric_discovery_limit", source=source_reference
                ),
            )
        )
    return MetricDiscoveryResult(
        signals=tuple(discovery.signals),
        relevant_distributions=("scikit-learn",) if discovery.signals else (),
    )
