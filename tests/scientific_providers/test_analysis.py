"""Parse reuse retains source admission, immutable facts and private tree authority."""

import ast
from dataclasses import FrozenInstanceError

import pytest

from apizr.experiments.provider_source import SourceView
from apizr.scientific_providers.builtin import BuiltinProvider
from apizr.scientific_providers.builtin.recognition import recognize_source
from apizr.scientific_providers.contracts import ProviderRequest


def test_revalidation_reuses_only_matching_immutable_facts(monkeypatch):
    source = SourceView(reference="s.py", text="value = 1\n")
    original = ast.parse
    calls = []

    def parsed(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(ast, "parse", parsed)
    first = ProviderRequest(provider=BuiltinProvider().descriptor, source=source)
    second = ProviderRequest.model_validate(first)
    assert second.source.analysis is source.analysis
    assert not calls
    with pytest.raises(FrozenInstanceError):
        source.analysis.byte_size = 0
    changed = SourceView.model_validate(
        source.model_copy(update={"text": "value = 2\n"})
    )
    assert len(calls) == 1 and changed.digest != source.digest
    changed.tree().body.clear()
    assert changed.tree().body and source.tree().body
    wire = SourceView.model_validate_json(source.model_dump_json())
    assert wire.model_dump_json() == source.model_dump_json()
    assert wire.analysis is not source.analysis
    assert "analysis" not in source.model_dump_json()
    with pytest.raises(ValueError, match="provider_source"):
        SourceView.model_validate(source.model_copy(update={"text": "invalid ("}))


@pytest.mark.parametrize("source", ["invalid (", "x=1\n" * 262145])
def test_shared_recognition_preserves_individual_admission_diagnostics(source):
    result = recognize_source(source, "s.py")
    assert result.input_reads.diagnostics and result.metric_signals.diagnostics
    assert (
        result.output_candidates.diagnostics and result.randomness_controls.diagnostics
    )


def test_shared_recognition_preserves_overflow_and_drops_location_trace():
    result = recognize_source("import random\n" + "random.seed(None)\n" * 513, "s.py")
    assert (
        result.randomness_controls.diagnostics[0].code == "randomness_discovery_limit"
    )
    assert result.inputs == result.controls == ()


def test_readiness_classifies_once_per_annotation_and_declaration_boundary(monkeypatch):
    import apizr.readiness.analysis as analysis
    from apizr.capabilities import inspect_source
    from apizr.readiness import assess

    text = "\n".join(f"def fn_{i}(x: float) -> float: return x" for i in range(100))
    document = inspect_source(text, module_name="s")
    original = analysis.classify
    calls = []

    def classify(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(analysis, "classify", classify)
    report = assess(document, text)
    assert len(report.assessments) == 100 and len(calls) == 1
