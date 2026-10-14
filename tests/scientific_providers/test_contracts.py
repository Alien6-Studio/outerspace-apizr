"""Scientific evidence remains source-bound untrusted input at core admission."""

import ast
import copy
import hashlib
import json
import subprocess
import sys

import pytest
from pydantic import ValidationError

from apizr.experiments.inputs import discover_inputs
from apizr.experiments.metrics import discover_metrics
from apizr.experiments.model import EvidenceOrigin
from apizr.experiments.outputs import discover_outputs
from apizr.experiments.provider_source import SourceLexicalVisitor, SourceView
from apizr.experiments.randomness import discover_randomness
from apizr.extension_runtime.protocol import Request, validate_response
from apizr.scientific_providers import (
    RECOGNIZE_OPERATION,
    ProducerIdentity,
    ProviderDescriptor,
    ProviderDiagnostic,
    ProviderLimits,
    ProviderLocation,
    ProviderRequest,
    ProviderResult,
    SDKAdapterDescriptor,
    admit_extension_response,
    admit_result,
    extension_arguments,
)

SOURCE = """import pandas as pd
import numpy as np
import joblib
from sklearn.metrics import accuracy_score
data = pd.read_csv("data.csv")
np.random.seed(7)
score = accuracy_score([1], [1])
joblib.dump(data, "model.joblib")
"""
CAPABILITIES = (
    "metric_signals",
    "output_candidates",
    "randomness_controls",
    "input_reads",
)


def request(*, source=SOURCE, capabilities=CAPABILITIES, limits=None):
    return ProviderRequest(
        provider=ProviderDescriptor(
            identity=ProducerIdentity(name="test.static", version="1.0"),
            capabilities=capabilities,
            limits=limits or ProviderLimits(),
        ),
        source=SourceView(reference="science.py", text=source),
    )


def result(value):
    source = value.source
    return ProviderResult(
        identity=value.provider.identity,
        source=source.reference,
        source_digest=source.digest,
        metric_signals=discover_metrics(source.text, source_reference=source.reference),
        output_candidates=discover_outputs(
            source.text, source_reference=source.reference
        ),
        randomness_controls=discover_randomness(
            source.text, source_reference=source.reference
        ),
        input_reads=discover_inputs(source.text, source_reference=source.reference),
    )


def test_existing_evidence_round_trips_without_new_metric_values_or_publication():
    selected = request()
    candidate = result(selected)
    admitted = admit_result(candidate, request=selected)
    assert admitted == candidate
    assert (
        admit_result(candidate.model_dump(mode="json"), request=selected) == candidate
    )
    assert (
        admit_result(admitted, request=selected).model_dump_json()
        == candidate.model_dump_json()
    )
    assert candidate.metric_signals.signals[0].name == "accuracy"
    assert candidate.input_reads.artifacts[0].digest is None
    assert candidate.input_reads.artifacts[0].origin == EvidenceOrigin.STATIC
    assert candidate.randomness_controls.controls[0].value == 7
    assert (
        candidate.output_candidates.signals[0].declaration.reference == "model.joblib"
    )
    assert selected.provider.capabilities == tuple(sorted(CAPABILITIES))
    assert (
        SourceView.model_validate_json(selected.source.model_dump_json())
        == selected.source
    )


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "apizr.scientific-result/v2"},
        {"identity": {"name": "other", "version": "1.0"}},
        {"identity": {"name": "test.static", "version": "2.0"}},
        {"source": "other.py"},
        {"source_digest": "f" * 64},
        {"observed_metrics": [{"name": "accuracy", "value": 1.0}]},
    ],
    ids=[
        "schema",
        "producer_name",
        "producer_version",
        "source_reference",
        "source_digest",
        "runtime_metric_field",
    ],
)
def test_identity_source_schema_and_unknown_fields_are_rejected(change):
    selected = request()
    payload = result(selected).model_dump(mode="json")
    payload.update(change)
    with pytest.raises(ValueError, match="^provider_result_invalid$"):
        admit_result(payload, request=selected)


@pytest.mark.parametrize("section", CAPABILITIES)
def test_capabilities_are_required_even_for_section_diagnostics(section):
    selected = request(capabilities=tuple(c for c in CAPABILITIES if c != section))
    with pytest.raises(ValueError, match="provider_result_invalid"):
        admit_result(result(selected), request=selected)


@pytest.mark.parametrize(
    "change",
    [
        {"origin": "runtime"},
        {"origin": "declared"},
        {"digest": "a" * 64, "content_origin": None},
        {"size": 0, "content_origin": None},
        {"content_origin": "runtime"},
    ],
    ids=["runtime", "declared", "digest", "size", "content_origin"],
)
def test_static_provider_cannot_assert_input_content_observations(change):
    selected = request()
    payload = result(selected).model_dump(mode="json")
    payload["input_reads"]["artifacts"][0].update(change)
    with pytest.raises(ValueError, match="provider_result_invalid"):
        admit_result(payload, request=selected)


@pytest.mark.parametrize(
    "section,item,change",
    [
        ("metric_signals", "signals", {"source": "other.py"}),
        ("output_candidates", "signals", {"line": 100}),
        ("metric_signals", "signals", {"column": 1000}),
        ("metric_signals", "signals", {"origin": "runtime"}),
        ("randomness_controls", "controls", {"origin": "runtime"}),
        ("randomness_controls", "controls", {"value": float("nan")}),
        ("randomness_controls", "controls", {"value": [0] * 1025}),
        ("randomness_controls", "controls", {"value": 2**63}),
        ("metric_signals", "signals", {"name": "f1"}),
    ],
)
def test_evidence_cannot_bypass_canonical_types_bounds_or_locations(
    section, item, change
):
    selected = request()
    payload = result(selected).model_dump(mode="json")
    payload[section][item][0].update(change)
    with pytest.raises(ValueError, match="provider_result_invalid"):
        admit_result(payload, request=selected)


def test_lowered_aggregate_limits_apply_across_sections():
    for limits in (
        ProviderLimits(max_evidence=1),
        ProviderLimits(max_result_bytes=100),
    ):
        selected = request(limits=limits)
        with pytest.raises(ValueError, match="provider_result_invalid"):
            admit_result(result(selected), request=selected)
    selected = request(limits=ProviderLimits(max_diagnostics=1))
    diag = ProviderDiagnostic(
        code="provider_limit", location=ProviderLocation(source="science.py")
    )
    candidate = result(selected).model_copy(update={"diagnostics": (diag, diag)})
    with pytest.raises(ValueError, match="provider_result_invalid"):
        admit_result(candidate, request=selected)


def test_diagnostics_retain_unknown_origin_and_source_or_precise_position():
    selected = request()
    diagnostic = ProviderDiagnostic(
        code="provider_unsupported",
        capability="metric_signals",
        location=ProviderLocation(source="science.py", line=7, column=8),
    )
    candidate = result(selected).model_copy(update={"diagnostics": (diagnostic,)})
    assert admit_result(candidate, request=selected).diagnostics == (diagnostic,)
    assert diagnostic.origin == EvidenceOrigin.UNKNOWN
    for location in (
        {"source": "other.py"},
        {"source": "science.py", "line": 1},
        {"source": "science.py", "line": 2, "column": 999},
    ):
        payload = candidate.model_dump(mode="json")
        payload["diagnostics"][0]["location"] = location
        with pytest.raises(ValueError, match="provider_result_invalid"):
            admit_result(payload, request=selected)
    payload = candidate.model_dump(mode="json")
    payload["diagnostics"][0]["capability"] = "input_reads"
    limited = request(capabilities=("metric_signals",))
    empty = ProviderResult(
        identity=limited.provider.identity,
        source="science.py",
        source_digest=limited.source.digest,
    )
    payload = empty.model_dump(mode="json") | {"diagnostics": payload["diagnostics"]}
    with pytest.raises(ValueError, match="provider_result_invalid"):
        admit_result(payload, request=limited)


@pytest.mark.parametrize(
    "change",
    [
        {"source": "other.py"},
        {"source": None, "line": 1, "column": 0},
        {"source": "science.py", "line": 1, "column": None},
    ],
)
def test_existing_section_diagnostics_are_revalidated(change):
    selected = request()
    payload = result(selected).model_dump(mode="json")
    payload["input_reads"]["diagnostics"] = [
        {"code": "dynamic_input_reference", **change}
    ]
    with pytest.raises(ValueError, match="provider_result_invalid"):
        admit_result(payload, request=selected)


def test_unknown_input_and_unknown_randomness_are_preserved():
    selected = request(source="import numpy as np\nnp.random.seed(seed)\n")
    candidate = result(selected)
    admitted = admit_result(candidate, request=selected)
    assert admitted.randomness_controls.controls[0].origin == EvidenceOrigin.UNKNOWN
    assert admitted.randomness_controls.controls[0].value is None
    assert admitted.randomness_controls.diagnostics[0].source == "science.py"


def test_tampered_instances_are_revalidated_and_error_content_is_redacted():
    selected = request()
    for invalid in (
        object(),
        {"secret": "PRIVATE"},
        selected.model_copy(
            update={
                "provider": selected.provider.model_copy(update={"capabilities": ()})
            }
        ),
    ):
        with pytest.raises(ValueError, match="^provider_result_invalid$") as error:
            admit_result(invalid, request=selected)
        assert "PRIVATE" not in str(error.value)
    invalid_request = selected.model_copy(
        update={"source": selected.source.model_copy(update={"reference": "../secret"})}
    )
    with pytest.raises(ValueError, match="provider_result_invalid"):
        admit_result(result(selected), request=invalid_request)


def test_extension_payload_uses_existing_wire_protocol_and_runtime_correlation():
    selected = request()
    arguments = extension_arguments(selected)
    wire = Request.model_validate(
        {
            "protocol": "apizr.extension/v1",
            "request_id": "a" * 32,
            "operation": RECOGNIZE_OPERATION,
            "arguments": arguments,
        }
    )
    payload = {
        "protocol": wire.protocol,
        "request_id": wire.request_id,
        "operation": wire.operation,
        "status": "ok",
        "result": result(selected).model_dump(mode="json"),
    }
    response = validate_response(json.dumps(payload).encode(), wire)
    assert admit_extension_response(response, request=selected) == result(selected)
    with pytest.raises(ValueError, match="provider_result_invalid"):
        admit_extension_response(
            response.model_copy(update={"operation": "describe"}), request=selected
        )
    with pytest.raises(ValueError, match="provider_result_invalid"):
        admit_extension_response(
            response.model_copy(update={"protocol": "other/v1"}), request=selected
        )
    with pytest.raises(Exception, match="protocol_invalid"):
        validate_response(json.dumps(payload | {"request_id": "b" * 32}).encode(), wire)


@pytest.mark.parametrize("model", [ProviderDescriptor, SDKAdapterDescriptor])
def test_descriptor_capabilities_and_observation_mode_are_strict(model):
    capability = "metric_signals" if model is ProviderDescriptor else "metric"
    identity = ProducerIdentity(name="test.adapter", version="0.1")
    assert model(identity=identity, capabilities=(capability,)).identity == identity
    for extra in (
        {"capabilities": (capability, capability)},
        {"capabilities": ()},
        {"capabilities": ("arbitrary",)},
        {"observation": "automatic-object-traversal"},
    ):
        with pytest.raises(ValidationError):
            model.model_validate(
                {"identity": identity, "capabilities": (capability,), **extra}
            )


def test_source_digest_tree_ownership_and_utf8_locations():
    view = SourceView(reference="module.py", text="label = 'é'\n")
    assert view.digest == hashlib.sha256(view.text.encode("utf-8")).hexdigest()
    tree = view.tree()
    tree.body.clear()
    assert len(view.tree().body) == 1
    assert view.contains_location(1, len(view.text.rstrip().encode()))
    assert not view.contains_location(0, 0)
    assert not view.contains_location(1, 100)
    assert not view.contains_location(2, 0)
    assert copy.deepcopy(view) == view


@pytest.mark.parametrize(
    "source",
    [
        "bad(",
        "a = '\ud800'",
        "#" + "é" * (512 * 1024),
        "x = [" + "0," * 100_001 + "]",
        "x = " + " + ".join(["1"] * 200),
    ],
    ids=["syntax", "unicode", "utf8_byte_limit", "ast_node_limit", "ast_depth_limit"],
)
def test_source_syntax_utf8_ast_depth_and_node_bounds(source):
    with pytest.raises(ValueError):
        SourceView(reference="module.py", text=source)


@pytest.mark.parametrize(
    "limit,value",
    [
        ("max_bytes", 0),
        ("max_bytes", 1024 * 1024 + 1),
        ("max_nodes", 1),
        ("max_depth", 1),
    ],
)
def test_source_view_can_only_lower_core_bounds(limit, value):
    source = SourceView(reference="module.py", text="x = 1")
    with pytest.raises(ValueError, match="provider_source_invalid_or_limit"):
        source.tree(**{limit: value})


@pytest.mark.parametrize(
    "limits",
    [
        ProviderLimits(max_source_bytes=1),
        ProviderLimits(max_ast_nodes=1),
        ProviderLimits(max_ast_depth=1),
    ],
)
def test_request_applies_declared_source_limits(limits):
    with pytest.raises(ValueError, match="provider_source_invalid_or_limit"):
        request(limits=limits)


def test_public_lexical_view_retains_alias_and_shadowing_authority():
    class Visitor(SourceLexicalVisitor):
        def __init__(self):
            super().__init__(
                lambda name: name == "numpy", lambda name: name == "numpy.load"
            )
            self.calls = []

        def visit_Call(self, node):
            self.calls.append(self.resolve_call(node))
            self.generic_visit(node)

    source = SourceView(
        reference="module.py",
        text="import numpy as np\nnp.load('a.npy')\ndef nested(np):\n    np.load('b.npy')\n",
    )
    visitor = Visitor()
    visitor.visit(source.tree())
    assert visitor.calls == ["numpy.load", ""]
    assert all(isinstance(node, ast.AST) for node in source.tree().body)


def test_contract_import_does_not_load_scientific_libraries_store_or_plugin_manager():
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            """import sys
import apizr.scientific_providers
assert not any(n in sys.modules for n in ('numpy', 'pandas', 'sklearn', 'torch', 'tensorflow', 'joblib'))
assert 'apizr.experiments.store' not in sys.modules
assert not any(n.startswith('apizr.plugins.') for n in sys.modules)
""",
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
