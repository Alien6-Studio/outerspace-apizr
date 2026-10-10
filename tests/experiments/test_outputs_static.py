"""Literal joblib output candidates are selections, never observed artifacts."""

import pytest
from pydantic import ValidationError

from apizr.experiments import (
    EvidenceOrigin as O,
)
from apizr.experiments import (
    OutputArtifact,
    OutputCaptureResult,
    OutputDeclaration,
    OutputDiagnostic,
    OutputDiscoveryResult,
    OutputSignal,
    discover_outputs,
    outputs,
    parse_output_declaration,
)


@pytest.mark.parametrize(
    "source",
    [
        'import joblib\njoblib.dump(model,"artifacts/model.joblib")',
        'import joblib as jl\njl.dump(model,"artifacts/model.joblib")',
        'from joblib import dump\ndump(model,"artifacts/model.joblib")',
        'from joblib import dump as save\nsave(model,"artifacts/model.joblib")',
        'import joblib\ndef train():\n joblib.dump(model,"artifacts/model.joblib")',
        'import joblib\njoblib.dump(value=model,filename="artifacts/model.joblib")',
        'import joblib\njoblib.dump(model,filename="artifacts/model.joblib",compress=3,protocol=None)',
        'import joblib\njoblib.dump(model,"artifacts/model.joblib",3,protocol=5)',
        'import joblib\njoblib.dump(model,"artifacts/model.joblib",3,5)',
    ],
)
def test_safe_joblib_aliases_and_filename_arguments(source):
    result = discover_outputs(source, source_reference="train.py")
    assert not result.diagnostics and result.relevant_distributions == ("joblib",)
    assert len(result.signals) == 1
    signal = result.signals[0]
    assert type(signal) is OutputSignal and signal.origin is O.STATIC
    assert not isinstance(signal, OutputArtifact)
    assert signal.callable_name == "joblib.dump"
    assert signal.declaration == OutputDeclaration(
        name="artifacts/model.joblib", reference="artifacts/model.joblib"
    )
    assert (
        "digest" not in signal.model_dump_json()
        and "size" not in signal.model_dump_json()
    )
    assert "runtime" not in result.model_dump_json()


@pytest.mark.parametrize(
    "expression",
    [
        "MODEL_PATH",
        "str(path)",
        'Path("model.joblib")',
        'f"model{suffix}.joblib"',
        "None",
        'b"model.joblib"',
        "42",
    ],
)
def test_dynamic_filename_is_unresolved(expression):
    result = discover_outputs(
        f"import joblib\njoblib.dump(model, {expression})", source_reference="train.py"
    )
    assert result.signals == () and result.relevant_distributions == ("joblib",)
    assert result.diagnostics[0].code == "dynamic_output_reference"


@pytest.mark.parametrize(
    "arguments",
    [
        "model",
        "",
        'filename="model.joblib"',
        "*args",
        "model,*args",
        'model,"model.joblib",**kwargs',
        'model,filename="model.joblib",**kwargs',
        'model,"model.joblib",filename="other.joblib"',
        'model,"model.joblib",value=other',
        'model,"model.joblib",unknown=True',
        'model,"model.joblib",1,2,3',
        'model,filename="a",filename="b"',
    ],
)
def test_ambiguous_or_unsupported_arguments(arguments):
    result = discover_outputs(
        f"import joblib\njoblib.dump({arguments})", source_reference="train.py"
    )
    assert not result.signals
    assert result.diagnostics[0].code == "unsupported_output_arguments"


@pytest.mark.parametrize(
    "reference",
    [
        "/private/secret.joblib",
        "../escape.joblib",
        "a/../b",
        "a//b",
        "a/",
        "~/model",
        "C:\\model",
        "https://private/model",
        "s3://bucket/model",
        "",
        "a\nsecret",
        "\ud800",
        "x" * 1025,
    ],
)
def test_bad_reference_redacted(reference):
    result = discover_outputs(
        f"import joblib\njoblib.dump(model, {reference!r})", source_reference="train.py"
    )
    assert result.signals == ()
    assert result.diagnostics[0].code == "nonportable_output_reference"
    assert (
        "private" not in result.model_dump_json()
        and "secret" not in result.model_dump_json()
    )


def test_long_portable_reference_requires_explicit_short_name():
    reference = "artifacts/" + "x" * 128
    result = discover_outputs(
        f"import joblib\njoblib.dump(model, {reference!r})", source_reference="train.py"
    )
    assert not result.signals and result.diagnostics[0].code == "output_name_required"
    assert parse_output_declaration("model=" + reference).reference == reference


@pytest.mark.parametrize(
    "source",
    [
        'joblib.dump(model,"model.joblib")',
        'dump = custom\ndump(model,"model.joblib")',
        'import joblib as jl\njl = custom\njl.dump(model,"model.joblib")',
        'import joblib as jl\ndef train(jl):\n jl.dump(model,"model.joblib")',
        'import joblib\njoblib.dump = custom\njoblib.dump(model,"model.joblib")',
        'dump(model,"model.joblib")\nfrom joblib import dump',
        'from joblib import *\ndump(model,"model.joblib")',
        'from joblib import dump\nfrom custom import *\ndump(model,"model.joblib")',
        'if enabled:\n import joblib\njoblib.dump(model,"model.joblib")',
        'from .joblib import dump\ndump(model,"model.joblib")',
        'import torch\ntorch.save(model,"model.pt")',
        'from joblib import dump as save\ndef train():\n save=custom\n save(model,"model.joblib")',
        'def train():\n joblib.dump(model,"model.joblib")\nimport joblib',
    ],
)
def test_untrusted_bindings_and_out_of_scope_serializers(source):
    result = discover_outputs(source, source_reference="train.py")
    assert result.signals == result.diagnostics == result.relevant_distributions == ()


def test_repeated_occurrences_not_collapsed():
    result = discover_outputs(
        b'import joblib\njoblib.dump(a,"model.joblib"); joblib.dump(b,"model.joblib")',
        source_reference="train.py",
    )
    assert len(result.signals) == 2
    assert result.signals[0].declaration == result.signals[1].declaration
    assert result.signals[0].column != result.signals[1].column
    assert OutputDiscoveryResult(signals=result.signals[::-1]).signals == result.signals
    with pytest.raises(ValidationError, match="duplicate_occurrence"):
        OutputDiscoveryResult(signals=(result.signals[0],) * 2)


@pytest.mark.parametrize(
    "source,reference",
    [
        ("not python !!!", "train.py"),
        (b"\xff", "train.py"),
        (42, "train.py"),
        ("", "/private/train.py"),
        ("", "\ud800"),
    ],
)
def test_invalid_source_redacted(source, reference):
    result = discover_outputs(source, source_reference=reference)
    assert result == OutputDiscoveryResult(
        diagnostics=(OutputDiagnostic(code="output_source_invalid"),)
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
    monkeypatch.setattr(outputs, bound, 1)
    result = discover_outputs(source, source_reference="train.py")
    assert result.diagnostics == (
        OutputDiagnostic(
            code="output_discovery_limit", source="train.py" if has_source else None
        ),
    )


@pytest.mark.parametrize(
    "call,count",
    [('joblib.dump(model,"model.joblib")', 257), ("joblib.dump(model,PATH)", 513)],
)
def test_result_bounds_refuse_partial_selection(call, count):
    result = discover_outputs(
        "import joblib\n" + (call + "\n") * count, source_reference="train.py"
    )
    assert not result.signals and not result.relevant_distributions
    assert result.diagnostics == (
        OutputDiagnostic(code="output_discovery_limit", source="train.py"),
    )


@pytest.mark.parametrize(
    "value",
    [
        42,
        "model",
        "model=",
        "=model.joblib",
        "model=/private/file",
        "model=../escape",
        "model=https://host/model",
        "model=a\nsecret",
        "model=\ud800",
        "x" * 1154,
    ],
)
def test_parser_refuses_invalid_without_echo(value):
    with pytest.raises(ValueError, match="^explicit_output_invalid$"):
        parse_output_declaration(value)


def test_explicit_declaration_and_result_validation():
    assert parse_output_declaration(
        "model=artifacts/model.joblib"
    ) == OutputDeclaration(name="model", reference="artifacts/model.joblib")
    assert parse_output_declaration(" model=model file.joblib").name == " model"
    with pytest.raises(ValidationError):
        OutputDeclaration(name="model", reference="model", digest="a" * 64)
    signal = discover_outputs(
        'import joblib\njoblib.dump(model,"model.joblib")', source_reference="train.py"
    ).signals[0]
    with pytest.raises(ValidationError):
        OutputSignal.model_validate(signal.model_copy(update={"origin": O.RUNTIME}))
    with pytest.raises(ValidationError):
        OutputDiscoveryResult(signals=(signal,) * 257)
    with pytest.raises(ValidationError):
        OutputDiscoveryResult(relevant_distributions=("torch",))
    a = OutputDiagnostic(code="output_source_invalid")
    b = OutputDiagnostic(code="output_missing", name="model")
    assert OutputDiscoveryResult(diagnostics=(b, a, a)).diagnostics == (a, b)
    assert OutputCaptureResult(diagnostics=(b, a, a)).diagnostics == (a, b)
    with pytest.raises(ValidationError):
        OutputDiscoveryResult(diagnostics=(a,) * 513)
