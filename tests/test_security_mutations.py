"""A mutation gate must never treat infrastructure failures as killed mutants."""

import runpy
from pathlib import Path

import pytest

validate_result = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts/security_mutations.py")
)["validate_result"]


@pytest.mark.parametrize(
    "body,code",
    [
        ("<testcase/>", 0),
        ('<testcase><error message="import failed"/></testcase>', 1),
        ("<testcase><skipped/></testcase>", 0),
        ('<testcase><failure message="Failed: Timeout"/></testcase>', 1),
        ('<testcase><failure message="SyntaxError: broken mutation"/></testcase>', 1),
        ('<testcase><failure message="assert False"/></testcase>', 2),
        ("", 5),
    ],
)
def test_bad_runs_are_not_successful_mutations(tmp_path, body, code):
    report = tmp_path / "result.xml"
    report.write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>")
    with pytest.raises(ValueError):
        validate_result(report, code, mutated=True)


@pytest.mark.parametrize(
    "message", ["assert False", "AssertionError: guard", "Failed: DID NOT RAISE"]
)
def test_only_designated_assertion_failures_kill_mutants(tmp_path, message):
    report = tmp_path / "result.xml"
    report.write_text(
        f'<testsuites><testsuite><testcase><failure message="{message}"/></testcase></testsuite></testsuites>'
    )
    validate_result(report, 1, mutated=True)
    with pytest.raises(ValueError):
        validate_result(report, 1, mutated=False)
