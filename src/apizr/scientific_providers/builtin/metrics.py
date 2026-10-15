"""Built-in metrics recognition; source syntax only, never scientific imports."""

import ast

from pydantic import TypeAdapter

from apizr.experiments.metrics import (
    MetricDiagnostic,
    MetricDiscoveryResult,
    MetricSignal,
)
from apizr.experiments.model import Reference
from apizr.experiments.provider_source import (
    MAX_DEPTH,
    MAX_NODES,
    MAX_SOURCE_BYTES,
    SourceLexicalVisitor,
    SourceLimit,
    bounded_tree,
)

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


class Discovery(SourceLexicalVisitor):
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
    discovery = Discovery(source_reference)
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
