"""Performance evidence must reject test loss, outcome drift and missing gates."""

import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = runpy.run_path(str(ROOT / "scripts/benchmark_pytest.py"))


def junit(path, cases, total=None):
    count = len(cases) if total is None else total
    path.write_text(
        f'<testsuites><testsuite tests="{count}">{"".join(cases)}</testsuite></testsuites>'
    )
    return path


PASS = '<testcase classname="tests.alpha" name="test_value[é]"/>'
SKIP = '<testcase classname="tests.beta" name="test_docker"><skipped/></testcase>'


def test_comparison_is_order_independent_and_retains_skips_and_duplicates(tmp_path):
    first = junit(tmp_path / "serial.xml", [PASS, SKIP, PASS])
    second = junit(tmp_path / "parallel.xml", [PASS, PASS, SKIP])
    result = TOOL["compare"](first, second)
    assert result["cases"] == 3
    assert result["outcomes"] == {"passed": 2, "skipped": 1}
    assert len(result["identities_sha256"]) == 64


@pytest.mark.parametrize(
    "after",
    [
        [PASS],
        [PASS, SKIP, PASS],
        [PASS, SKIP.replace("<skipped/>", "")],
        [PASS.replace("[é]", "[e]"), SKIP],
    ],
)
def test_comparison_rejects_case_loss_duplicates_skip_drift_and_changed_ids(
    tmp_path, after
):
    with pytest.raises(
        ValueError, match="identities, outcomes or multiplicities differ"
    ):
        TOOL["compare"](
            junit(tmp_path / "serial.xml", [PASS, SKIP]),
            junit(tmp_path / "parallel.xml", after),
        )


@pytest.mark.parametrize(
    "cases,total",
    [
        ([], 0),
        ([SKIP], 1),
        ([PASS], 2),
        ([PASS.replace("/>", "><failure/></testcase>")], 1),
        ([SKIP.replace("<skipped/>", "<skipped/><error/>")], 1),
    ],
)
def test_junit_refuses_empty_skipped_incomplete_or_failed_evidence(
    tmp_path, cases, total
):
    with pytest.raises(ValueError):
        TOOL["cases"](junit(tmp_path / "tests.xml", cases, total))


def test_benchmark_uses_every_current_compatibility_coverage_floor():
    gates = TOOL["coverage_gates"]()
    assert len(gates) >= 23
    assert any("scripts/check_scope_coverage.py" in gate for gate in gates)
    assert any("--fail-under=59.5" in gate for gate in gates)
    assert sum("--fail-under=90" in gate for gate in gates) >= 21


def test_benchmark_refuses_a_source_with_missing_coverage_gates(tmp_path, monkeypatch):
    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("jobs:\n  compatibility:\n    steps: []\n")
    monkeypatch.setitem(TOOL["coverage_gates"].__globals__, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="Missing compatibility coverage gates"):
        TOOL["coverage_gates"]()
