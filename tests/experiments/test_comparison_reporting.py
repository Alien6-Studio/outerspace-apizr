"""Reports remain factual and bounded, with full IDs and visible uncertainty."""

from apizr.experiments import EvidenceOrigin, Metric, PackageEvidence, Parameter
from apizr.experiments import comparison_reporting as report
from apizr.experiments.comparison import compare_runs

from .comparison_support import record, replace


def test_all_sections_and_numeric_delta():
    a = record(
        metrics=(Metric(name="roc_auc", value=0.941, origin=EvidenceOrigin.RUNTIME),)
    )
    b = record(
        metrics=(Metric(name="roc_auc", value=0.948, origin=EvidenceOrigin.RUNTIME),)
    )
    text = report.diff_text(compare_runs(a, b))
    assert text.startswith("Experiment diff — A → B")
    assert text.endswith(report.DISCLAIMER)
    for digest in (a.run_digest, b.run_digest, a.plan_digest, b.plan_digest):
        assert digest in text
    for heading in (
        "Code",
        "Data",
        "Parameters",
        "Randomness",
        "Environment",
        "Serving",
        "Status",
        "Metrics",
        "Outputs",
    ):
        assert heading in text
    assert (
        text.index("Material evidence differences")
        < text.index("Observed result differences")
        < text.index("Metrics")
    )
    assert "delta B - A: +0.007" in text
    assert "UNKNOWN" in text
    assert "experiments are identical" not in text


def test_missing_evidence_and_non_numeric_metric():
    a = record()
    b = record(
        metrics=(
            Metric(
                name="structured",
                value={"precision": 0.88, "recall": 0.82},
                origin=EvidenceOrigin.RUNTIME,
            ),
        ),
        outputs=(),
        effective_parameters=(),
        environment=None,
        plan=replace(a.plan, parameters=(), inputs=(), randomness=()),
    )
    text = report.diff_text(compare_runs(a, b))
    assert "not recorded" in text and "REMOVED" in text and "ADDED" in text
    assert "delta B - A" not in text
    assert "No material recorded differences" not in text
    assert "fraud-model evidence — REMOVED" in text


def test_section_value_and_total_limits(monkeypatch):
    a = record()
    environment = replace(
        a.run.environment,
        packages=tuple(
            PackageEvidence(
                name=f"package-{i:03d}", version="1.0", origin=EvidenceOrigin.RUNTIME
            )
            for i in range(201)
        ),
    )
    a = record(
        environment=environment,
        effective_parameters=(
            Parameter(name="long", value="é" * 1000, origin=EvidenceOrigin.RUNTIME),
        ),
    )
    result = compare_runs(a, a)
    text = report.diff_text(result)
    assert "…" in text and report.TRUNCATED in text
    assert "package-199" in text and "package-200" not in text
    assert len(text.encode()) < report.MAX_TEXT_BYTES
    monkeypatch.setattr(report, "MAX_TEXT_BYTES", 2000)
    text = report.diff_text(result)
    assert report.TRUNCATED in text and text.endswith(report.DISCLAIMER)
    assert len(text.encode()) <= 2000
    assert a.run_digest in text and a.plan_digest in text


def test_optional_source_fields_render_unknown():
    a = record()
    a = record(
        plan=replace(
            a.plan, subject=replace(a.plan.subject, executable_digest=None, module=None)
        )
    )
    assert "executable_digest: A unknown; B unknown — UNKNOWN" in report.diff_text(
        compare_runs(a, a)
    )
