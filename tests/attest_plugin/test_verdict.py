import pytest
from apizr_attest.model import AttestError
from apizr_attest.verdict import validate_verdict
from test_delivery import verdict


@pytest.mark.parametrize(
    "receipt",
    [None, "", "other.yaml", "../receipt.yaml", "/receipt.yaml", ["receipt.yaml"]],
)
def test_receipt_identity_refused(receipt):
    report = verdict()
    report["receipt"] = receipt
    with pytest.raises(AttestError, match="^receipt_verification_failed$"):
        validate_verdict(report, "3" * 64)


@pytest.mark.parametrize(
    "field", ["receipt", "verdict", "signed_by", "warnings", "checks"]
)
def test_missing_field_refused(field):
    report = verdict()
    del report[field]
    with pytest.raises(AttestError, match="^receipt_verification_failed$"):
        validate_verdict(report, "3" * 64)


def test_unknown_field_refused():
    report = verdict()
    report["policy"] = "weaker"
    with pytest.raises(AttestError, match="^receipt_verification_failed$"):
        validate_verdict(report, "3" * 64)


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", []),
        ("name", {}),
        ("name", None),
        ("name", "future"),
        ("detail", None),
        ("detail", []),
        ("status", True),
        ("status", "fail"),
        ("extra", "value"),
    ],
)
def test_malformed_check_refused(field, value):
    report = verdict()
    report["checks"][0][field] = value
    with pytest.raises(AttestError, match="^receipt_verification_failed$"):
        validate_verdict(report, "3" * 64)


@pytest.mark.parametrize("field", ["name", "status", "detail"])
def test_missing_check_field_refused(field):
    report = verdict()
    del report["checks"][0][field]
    with pytest.raises(AttestError, match="^receipt_verification_failed$"):
        validate_verdict(report, "3" * 64)


@pytest.mark.parametrize("check", [None, [], "pass", True])
def test_nonobject_check_refused(check):
    report = verdict()
    report["checks"][0] = check
    with pytest.raises(AttestError, match="^receipt_verification_failed$"):
        validate_verdict(report, "3" * 64)


def test_check_order_and_diagnostic_text_do_not_authorize():
    report = verdict()
    report["checks"].reverse()
    report["checks"][0]["detail"] = ""
    validate_verdict(report, "3" * 64)
    report["checks"][0]["detail"] = "pass"
    report["checks"][0]["status"] = "fail"
    with pytest.raises(AttestError, match="^receipt_verification_failed$"):
        validate_verdict(report, "3" * 64)
