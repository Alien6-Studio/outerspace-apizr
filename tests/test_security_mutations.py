"""A mutation gate must never treat infrastructure failures as killed mutants."""

import ast
import json
import runpy
import sys
from pathlib import Path

import pytest
from qualification_scripts import implementation as qualification_script

from scripts.qualification.ci import security_mutations

validate_result = runpy.run_path(str(qualification_script("security_mutations")))[
    "validate_result"
]


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


def test_mutation_targets_keep_their_unique_executable_source_anchors():
    root = Path(__file__).resolve().parents[1]
    for mutation in security_mutations.MUTATIONS:
        source = (root / mutation.path).read_text()
        assert source.count(mutation.before) == 1, mutation.name
        ast.parse(source.replace(mutation.before, mutation.after, 1))


def test_disposable_checkout_kills_the_moved_license_mutation(tmp_path, monkeypatch):
    mutation = next(
        item
        for item in security_mutations.MUTATIONS
        if item.name == "development-license-cannot-reach-runtime"
    )
    monkeypatch.setattr(security_mutations, "MUTATIONS", (mutation,))
    output = tmp_path / "evidence"
    monkeypatch.setattr(sys, "argv", ["security_mutations", "--output", str(output)])
    security_mutations.main()
    evidence = json.loads((output / "summary.json").read_text())
    assert evidence == {
        "baseline": "passed",
        "mutations": [
            {"name": mutation.name, "test": mutation.test, "result": "killed"}
        ],
    }
