import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from apizr.capabilities import CapabilityDocument, canonical_bytes, document_digest
from apizr.capabilities import inspect_source as capabilities
from apizr.inspection import Inspection, inspect_source, json_bytes
from apizr.readiness import ReadinessReport, assess, report_digest
from apizr.readiness import canonical_bytes as readiness_bytes
from apizr.readiness.model import Code, Dimension, Reason, State

ROOT = Path(__file__).resolve().parents[2]


def test_ir_schema_golden_and_canonical_digest_are_pinned_to_merged_v1():
    expected = {
        "docs/specs/apizr-capability-v1.schema.json": "ac531780dba1a63a187d62cd7e65fd809dfdc2e43bdfa1b6161b80f73d1839e7",
        "tests/fixtures/capability_ir/v1/basic.json": "f16af83a24e631823c364beeea15500672355f5b1ddfdd89ec0536bb4facb28c",
    }
    for path, digest in expected.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    source = (ROOT / "tests/fixtures/capability_ir/v1/basic.py").read_bytes()
    ir = inspect_source(source, module_name="pricing").capability_ir
    golden = CapabilityDocument.model_validate_json(
        (ROOT / "tests/fixtures/capability_ir/v1/basic.json").read_bytes()
    )
    assert canonical_bytes(ir) == canonical_bytes(golden)
    assert (
        document_digest(ir).value
        == "60902677ce6b84838694d47b70b995f7d3020fca0f3ab876052e73f149fc1846"
    )
    assert (
        json.loads((ROOT / "docs/specs/apizr-capability-v1.schema.json").read_bytes())
        == CapabilityDocument.model_json_schema()
    )


def test_separate_artifacts_round_trip_and_bind_their_digests():
    inspection = inspect_source("def café(x: int): return x", module_name="café")
    assert Inspection.model_validate_json(json_bytes(inspection)) == inspection
    report = inspection.readiness
    assert ReadinessReport.model_validate_json(readiness_bytes(report)) == report
    assert (
        report_digest(report).value
        == hashlib.sha256(readiness_bytes(report)).hexdigest()
    )
    assert inspection.ir_digest == document_digest(inspection.capability_ir)
    assert (
        len(
            {
                inspection.ir_digest.value,
                inspection.readiness_digest.value,
                report.source.digest.value,
            }
        )
        == 3
    )
    assert readiness_bytes(report).endswith(b"\n")
    assert b"\n" not in readiness_bytes(report)[:-1]
    assert "café".encode() in readiness_bytes(report)
    assert json.loads(json_bytes(inspection))["schema_version"] == "apizr.inspection/v1"
    assert report.policy_version == "apizr.readiness/v1"


def test_evidence_must_match_the_exact_ir_source_and_declarations():
    ir = capabilities("def f(): pass", module_name="matching")
    with pytest.raises(ValueError, match="source digest"):
        assess(ir, "def f(): pass\n")
    modified = ir.model_dump(mode="json")
    modified["capabilities"][0]["docstring"] = "fabricated"
    with pytest.raises(ValueError, match="declarations"):
        assess(CapabilityDocument.model_validate(modified), "def f(): pass")


def test_reason_order_and_states_cannot_be_manually_contradicted():
    first = Reason(code=Code.REBOUND, line=3)
    second = Reason(code=Code.NAMESPACE, line=1)
    value = Dimension.assess((first, second, first))
    assert value.reasons == (second, first)
    assert value.state == State.CONDITIONAL
    with pytest.raises(ValidationError, match="derive"):
        Dimension(state=State.READY, reasons=(first,))


@pytest.mark.parametrize(
    "mutation",
    [
        "state",
        "eligibility",
        "identity",
        "duplicates",
        "module",
        "ir_digest",
        "readiness_digest",
    ],
)
def test_inconsistent_report_models_are_rejected(mutation):
    data = inspect_source("def f(): pass", module_name="model").model_dump(mode="json")
    report = data["readiness"]
    value = report["assessments"][0]
    if mutation == "state":
        value["state"] = "unsupported"
    elif mutation == "eligibility":
        value["can_generate_interface"] = False
    elif mutation == "identity":
        value["capability_id"] = "python:other:f"
    elif mutation == "duplicates":
        report["assessments"].append(value)
    elif mutation == "module":
        report["source"]["module"] = "other"
    elif mutation == "ir_digest":
        data["ir_digest"]["value"] = "0" * 64
    else:
        data["readiness_digest"]["value"] = "0" * 64
    with pytest.raises(ValidationError):
        Inspection.model_validate(data)


def test_overload_input_contracts_are_not_discarded_as_untyped_implementation():
    result = inspect_source(
        "from typing import overload, Callable\n@overload\ndef f(x: Callable): ...\ndef f(x): return x",
        module_name="overloads",
    )
    assert result.readiness.assessments[0].dimensions.inputs.state == State.UNSUPPORTED
