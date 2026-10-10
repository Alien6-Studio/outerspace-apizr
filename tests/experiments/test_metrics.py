"""Static call occurrences cannot grant runtime metric values."""

import json
from types import MappingProxyType

import pytest
from pydantic import ValidationError

from apizr.experiments import (
    EvidenceOrigin as O,
)
from apizr.experiments import (
    Metric,
    MetricDiagnostic,
    MetricDiscoveryResult,
    MetricSignal,
    capture_metric,
    discover_metrics,
    metrics,
)


@pytest.mark.parametrize(
    "value",
    [
        0,
        -42,
        2**63 - 1,
        0.91,
        -0.0,
        None,
        True,
        "label",
        [0.91, 0.89],
        {"precision": 0.87, "recall": 0.82},
        {"nested": [None, False, {"value": 1}]},
    ],
)
def test_explicit_finite_values_preserve_types(value):
    metric = capture_metric("score", value)
    assert type(metric) is Metric and metric.origin is O.RUNTIME
    assert json.loads(metric.model_dump_json())["value"] == value
    assert Metric.model_validate_json(metric.model_dump_json()) == metric


def test_structures_are_deeply_immutable_and_detached():
    value = {"scores": [0.91, {"precision": 0.87}]}
    metric = capture_metric("classification", value)
    value["scores"][1]["precision"] = 0
    assert isinstance(metric.value, MappingProxyType)
    assert metric.value["scores"][1]["precision"] == 0.87
    with pytest.raises(TypeError):
        metric.value["scores"][1]["precision"] = 0


class Untrusted:
    def __repr__(self):
        raise AssertionError("arbitrary object repr must not be called")


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        -float("inf"),
        {"x": [float("nan")]},
        2**63,
        -(2**63) - 1,
        Untrusted(),
        RuntimeError("private"),
        b"bytes",
        {1: "wrong key"},
        set(),
        "x" * 8193,
        [0] * 1025,
        {str(i): i for i in range(1025)},
        {"x" * 257: 1},
        "\ud800",
        ["x" * 8192] * 9,
    ],
)
def test_rejected_values_are_not_stringified(value):
    with pytest.raises(ValueError, match="^metric_capture_invalid$"):
        capture_metric("score", value)


def test_recursive_deep_and_excess_nodes_refused():
    recursive = []
    recursive.append(recursive)
    deep = None
    for _ in range(18):
        deep = [deep]
    for value in (recursive, deep, [[0] * 1024] * 4):
        with pytest.raises(ValueError, match="^metric_capture_invalid$"):
            capture_metric("score", value)


@pytest.mark.parametrize("value", [1, 0.91, -0.0])
def test_unit_requires_numeric_scalar(value):
    assert capture_metric("latency", value, unit="ms").unit == "ms"


@pytest.mark.parametrize("value", [None, True, "0.91", [0.91], {"score": 0.91}])
def test_nonnumeric_or_structured_unit_rejected(value):
    with pytest.raises(ValueError, match="^metric_capture_invalid$"):
        capture_metric("score", value, unit="ms")
    with pytest.raises(ValidationError, match="unit_requires_numeric_scalar"):
        Metric(name="score", value=value, unit="ms", origin=O.RUNTIME)


@pytest.mark.parametrize(
    "name,unit",
    [
        ("", None),
        ("x" * 129, None),
        ("private\nname", None),
        ("score", ""),
        ("score", "x" * 65),
        ("score", "\ud800"),
    ],
)
def test_capture_metadata_redacted(name, unit):
    with pytest.raises(ValueError, match="^metric_capture_invalid$"):
        capture_metric(name, 0.91, unit=unit)


CALLABLES = [
    ("accuracy_score", "accuracy"),
    ("precision_score", "precision"),
    ("recall_score", "recall"),
    ("f1_score", "f1"),
    ("roc_auc_score", "roc_auc"),
    ("mean_squared_error", "mean_squared_error"),
]


@pytest.mark.parametrize("callable_name,name", CALLABLES)
@pytest.mark.parametrize(
    "template",
    [
        "import sklearn\nsklearn.metrics.{call}(y,p)",
        "import sklearn.metrics\nsklearn.metrics.{call}(y,p)",
        "import sklearn.metrics as metrics\nmetrics.{call}(y,p)",
        "from sklearn import metrics\nmetrics.{call}(y,p)",
        "from sklearn.metrics import {call}\n{call}(y,p)",
        "from sklearn.metrics import {call} as score\nscore(y,p)",
        "from sklearn.metrics import {call}\ndef train():\n    return {call}(y,p)",
    ],
)
def test_six_callables_and_safe_aliases(callable_name, name, template):
    result = discover_metrics(
        template.format(call=callable_name), source_reference="train.py"
    )
    assert len(result.signals) == 1 and not result.diagnostics
    signal = result.signals[0]
    assert type(signal) is MetricSignal and not isinstance(signal, Metric)
    assert signal.name == name
    assert signal.callable_name == "sklearn.metrics." + callable_name
    assert signal.origin is O.STATIC
    assert (
        "value" not in signal.model_dump() and "value" not in MetricSignal.model_fields
    )
    assert result.relevant_distributions == ("scikit-learn",)


@pytest.mark.parametrize(
    "source",
    [
        "roc_auc_score = custom\nroc_auc_score(y,p)",
        "import sklearn.metrics as metrics\nmetrics = custom\nmetrics.roc_auc_score(y,p)",
        "import sklearn.metrics as metrics\ndef train(metrics):\n return metrics.roc_auc_score(y,p)",
        "roc_auc_score(y,p)\nfrom sklearn.metrics import roc_auc_score",
        "from sklearn.metrics import *\nroc_auc_score(y,p)",
        "from sklearn.metrics import roc_auc_score\nfrom custom import *\nroc_auc_score(y,p)",
        "if flag:\n from sklearn.metrics import roc_auc_score\nroc_auc_score(y,p)",
        "from .sklearn.metrics import roc_auc_score\nroc_auc_score(y,p)",
        "import fake.metrics as metrics\nmetrics.roc_auc_score(y,p)",
        "import sklearn.metrics as metrics\nmetrics.roc_auc_score = custom\nmetrics.roc_auc_score(y,p)",
        "import sklearn.metrics as metrics\nmetrics.unknown(y,p)",
        "from sklearn.metrics import roc_auc_score as score\ndef train():\n score = custom\n return score(y,p)",
        "def train():\n return metrics.roc_auc_score(y,p)\nimport sklearn.metrics as metrics",
    ],
)
def test_untrusted_bindings_do_not_grant_metric_authority(source):
    result = discover_metrics(source, source_reference="train.py")
    assert result.signals == () and result.relevant_distributions == ()


def test_each_occurrence_retained_and_arguments_not_interpreted():
    source = b"from sklearn.metrics import roc_auc_score as auc\na=auc(); b=auc(hostile(), **kwargs)\n"
    result = discover_metrics(source, source_reference="train.py")
    assert [(s.name, s.line, s.column) for s in result.signals] == [
        ("roc_auc", 2, 2),
        ("roc_auc", 2, 11),
    ]
    assert MetricDiscoveryResult(signals=result.signals[::-1]).signals == result.signals
    with pytest.raises(ValidationError, match="duplicate_occurrence"):
        MetricDiscoveryResult(signals=(result.signals[0],) * 2)
    with pytest.raises(ValidationError, match="name_mismatch"):
        MetricSignal.model_validate(
            result.signals[0].model_copy(update={"name": "precision"})
        )


@pytest.mark.parametrize(
    "source,reference",
    [
        ("not python !!!", "train.py"),
        (b"\xff", "train.py"),
        (42, "train.py"),
        ("", "/secret/train.py"),
        ("", "\ud800"),
    ],
)
def test_invalid_source_redacted(source, reference):
    result = discover_metrics(source, source_reference=reference)
    assert result == MetricDiscoveryResult(
        diagnostics=(MetricDiagnostic(code="metric_source_invalid"),)
    )


@pytest.mark.parametrize(
    "bound,source,has_source",
    [
        ("MAX_SOURCE_BYTES", "#" * 30, False),
        ("MAX_NODES", "x=1", True),
        ("MAX_DEPTH", "x=1", True),
    ],
)
def test_source_bounds(monkeypatch, bound, source, has_source):
    monkeypatch.setattr(metrics, bound, 1)
    result = discover_metrics(source, source_reference="train.py")
    assert result.diagnostics == (
        MetricDiagnostic(
            code="metric_discovery_limit", source="train.py" if has_source else None
        ),
    )


def test_signal_bound_refuses_whole_batch():
    result = discover_metrics(
        "from sklearn.metrics import roc_auc_score\n" + "roc_auc_score(y,p)\n" * 257,
        source_reference="train.py",
    )
    assert not result.signals and not result.relevant_distributions
    assert result.diagnostics[0].code == "metric_discovery_limit"


def test_strict_result_and_static_origin():
    signal = discover_metrics(
        "from sklearn.metrics import roc_auc_score\nroc_auc_score(y,p)",
        source_reference="train.py",
    ).signals[0]
    for changes in (
        {"value": 0.91},
        {"origin": O.RUNTIME},
        {"line": 0},
        {"source": "../private"},
    ):
        with pytest.raises(ValidationError):
            MetricSignal.model_validate({**signal.model_dump(), **changes})
    with pytest.raises(ValidationError):
        MetricDiscoveryResult(signals=(signal,) * 257)
    with pytest.raises(ValidationError):
        MetricDiscoveryResult(relevant_distributions=("numpy",))
    d = MetricDiagnostic(code="metric_source_invalid")
    assert MetricDiscoveryResult(diagnostics=(d, d)).diagnostics == (d,)
    with pytest.raises(ValidationError):
        MetricDiscoveryResult(diagnostics=(d,) * 513)
