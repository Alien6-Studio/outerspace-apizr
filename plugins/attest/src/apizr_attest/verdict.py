"""Acceptance policy for the pinned Attest 0.1.0 native JSON verdict."""

from .model import AttestError

CHECKS = frozenset({"schema", "consistency", "signature", "timestamp", "recompute"})
FIELDS = frozenset({"receipt", "verdict", "signed_by", "warnings", "checks"})
CHECK_FIELDS = frozenset({"name", "status", "detail"})


def validate_verdict(report: object, expected_signer: str) -> None:
    # Bind the response to the exact relative argument passed to the verifier.
    # A successful verdict for a different receipt cannot authorize this proof.
    if (
        not isinstance(report, dict)
        or set(report) != FIELDS
        or report.get("receipt") != "receipt.yaml"
        or report.get("verdict") != "pass"
        or report.get("signed_by") != expected_signer
        or report.get("warnings") != []
    ):
        raise AttestError("receipt_verification_failed")
    checks = report.get("checks")
    if not isinstance(checks, list) or len(checks) != len(CHECKS):
        raise AttestError("receipt_verification_failed")
    names = set()
    for check in checks:
        if (
            not isinstance(check, dict)
            or set(check) != CHECK_FIELDS
            or not isinstance(check.get("name"), str)
            or not isinstance(check.get("detail"), str)
            or check.get("status") != "pass"
        ):
            raise AttestError("receipt_verification_failed")
        names.add(check["name"])
    if names != CHECKS:
        raise AttestError("receipt_verification_failed")
