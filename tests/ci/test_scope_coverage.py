"""Moved selected-evidence proofs retain their aggregate coverage obligation."""

import pytest

from scripts.qualification.ci.check_scope_coverage import (
    SELECTED_EVIDENCE,
    selected_summary,
)


def test_every_selected_proof_contributes_to_coverage():
    files = {
        name: {
            "summary": {
                "covered_lines": 100,
                "num_statements": 100,
                "covered_branches": 100,
                "num_branches": 100,
            }
        }
        for name in SELECTED_EVIDENCE
    }
    files["src/apizr/exposure/scope_admission.py"]["summary"].update(
        covered_lines=0, covered_branches=0
    )
    summary = selected_summary(files)
    assert summary["covered_lines"] / summary["num_statements"] == 0.8
    assert summary["covered_branches"] / summary["num_branches"] == 0.8


@pytest.mark.parametrize("missing", SELECTED_EVIDENCE)
def test_missing_coverage_for_any_proof_fails_closed(missing):
    files = {
        name: {
            "summary": dict.fromkeys(
                ("covered_lines", "num_statements", "covered_branches", "num_branches"),
                0,
            )
        }
        for name in SELECTED_EVIDENCE
        if name != missing
    }
    with pytest.raises(KeyError, match=missing):
        selected_summary(files)
