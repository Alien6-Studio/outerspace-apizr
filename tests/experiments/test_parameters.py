"""Only bounded, direct literals become candidates, never evaluated parameters."""

import ast

import pytest

from apizr.experiments import EvidenceOrigin, Parameter
from apizr.experiments.parameters import (
    ParameterDiscoveryResult,
    ParameterSignal,
    discover_parameters,
)


@pytest.mark.parametrize(
    "expression, expected",
    [
        ("None", None),
        ("True", True),
        ("False", False),
        ("8", 8),
        ("-8", -8),
        ("+0.05", 0.05),
        ("'rf'", "rf"),
        ("[1, 'x', None]", [1, "x", None]),
        ("(1, 2)", [1, 2]),
        ("{'a': [1, {'b': False}]}", {"a": [1, {"b": False}]}),
    ],
)
def test_literal_candidates(expression, expected):
    result = discover_parameters(
        f"learning_rate: object = {expression}", source_reference="train.py"
    )
    assert not result.diagnostics
    (signal,) = result.signals
    assert signal.parameter.model_dump(mode="json")["value"] == expected
    assert signal.parameter.origin == EvidenceOrigin.STATIC
    assert (signal.line, signal.column, signal.source) == (1, 0, "train.py")


@pytest.mark.parametrize(
    "expression, code",
    [
        ("config.depth", "dynamic_parameter_value"),
        ("float(os.environ['LR'])", "dynamic_parameter_value"),
        ("choose_value()", "dynamic_parameter_value"),
        ("1 + 2", "dynamic_parameter_value"),
        ("other", "dynamic_parameter_value"),
        ("+True", "dynamic_parameter_value"),
        ("{1: 'a'}", "parameter_literal_invalid"),
        ("{'a': 1, 'a': 2}", "parameter_literal_invalid"),
        ("{**other}", "parameter_literal_invalid"),
        ("b'abc'", "parameter_literal_invalid"),
        ("1j", "parameter_literal_invalid"),
        ("1e999", "parameter_literal_invalid"),
        (str(2**63), "parameter_literal_invalid"),
        (repr("x" * 8193), "parameter_literal_invalid"),
        ("[" * 18 + "1" + "]" * 18, "parameter_literal_invalid"),
        ("[" + ",".join("1" for _ in range(4097)) + "]", "parameter_literal_invalid"),
    ],
)
def test_dynamic_or_nonfinite_is_diagnostic(expression, code):
    result = discover_parameters(f"p = {expression}", source_reference="train.py")
    assert not result.signals
    assert [d.code for d in result.diagnostics] == [code]


def test_scope_and_occurrences():
    source = "a = b = 2\na = 3\nx: int\nx.y = 1\na, b = 1, 2\nif True:\n z = 3\ndef f():\n z = 4\nclass C:\n z = 5\n"
    result = discover_parameters(source, source_reference="train.py")
    assert [
        (s.parameter.name, s.parameter.value, s.line, s.column) for s in result.signals
    ] == [("a", 2, 1, 0), ("b", 2, 1, 4), ("a", 3, 2, 0)]
    assert [d.code for d in result.diagnostics] == [
        "dynamic_parameter_value",
        "parameter_assignment_unsupported",
        "parameter_assignment_unsupported",
    ]


@pytest.mark.parametrize(
    "source, reference, code",
    [
        ("x =", "train.py", "parameter_source_invalid"),
        (b"\xff", "train.py", "parameter_source_invalid"),
        ("x=1", "../train.py", "parameter_source_invalid"),
        (None, "train.py", "parameter_source_invalid"),
        ("#" * (1024 * 1024 + 1), "train.py", "parameter_discovery_limit"),
        ("x=1\n" * 257, "train.py", "parameter_discovery_limit"),
        ("x=f()\n" * 513, "train.py", "parameter_discovery_limit"),
    ],
)
def test_invalid_and_bounded(source, reference, code):
    result = discover_parameters(source, source_reference=reference)
    assert not result.signals
    assert [d.code for d in result.diagnostics] == [code]


def test_strict_origin_duplicates_and_order():
    result = discover_parameters("b=2\na=1", source_reference="train.py")
    assert ParameterDiscoveryResult(signals=tuple(reversed(result.signals))) == result
    with pytest.raises(ValueError, match="duplicate"):
        ParameterDiscoveryResult(signals=(result.signals[0],) * 2)
    for origin in (
        EvidenceOrigin.RUNTIME,
        EvidenceOrigin.UNKNOWN,
        EvidenceOrigin.DECLARED,
    ):
        with pytest.raises(ValueError, match="origin"):
            ParameterSignal(
                parameter=Parameter(name="x", value=None, origin=origin),
                source="train.py",
                line=1,
                column=0,
            )


def test_no_literal_eval_or_eval(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("parameter evaluation")

    monkeypatch.setattr(ast, "literal_eval", forbidden)
    assert discover_parameters(
        "p={'x': [1, -2.0]}", source_reference="train.py"
    ).signals
