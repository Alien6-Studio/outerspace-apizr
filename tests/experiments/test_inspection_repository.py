"""Reuse canonical, exactly bound repository and selection-scoped conclusions."""

import pytest

from apizr.experiments.inspection import enrich_serving, inspect_experiment
from apizr.experiments.inspection_model import ExperimentInspection
from apizr.experiments.reporting import text_report
from apizr.graph import build_graph
from apizr.repository import scan_sources
from apizr.repository_readiness import assess_repository
from apizr.repository_views.model import ViewQuery
from apizr.repository_views.projection import readiness_view

from .inspection_support import write_source


def evidence(files):
    catalog = scan_sources(files.items())
    graph = build_graph(
        catalog,
        {s.path: files[s.path] for s in catalog.sources if s.inspection is not None},
    )
    return catalog, graph, assess_repository(catalog, graph)


@pytest.mark.parametrize(
    "source", ["def predict(x: float) -> float:\n return x\n", "x = 1\n"]
)
def test_exact_reuse_without_rescan(tmp_path, monkeypatch, source):
    path = write_source(tmp_path, source)
    inspection = inspect_experiment(path)
    catalog, graph, report = evidence({"train.py": source.encode()})
    expected = (
        readiness_view(
            catalog,
            graph,
            report,
            ViewQuery(view="detail", capability_id="python:train:predict"),
        )
        if inspection.serving.capabilities
        else None
    )

    def forbidden(*args, **kwargs):
        pytest.fail("repository enrichment read filesystem")

    monkeypatch.setattr(type(path), "read_bytes", forbidden)
    monkeypatch.setattr(type(path), "read_text", forbidden)
    result = enrich_serving(inspection, catalog=catalog, graph=graph, readiness=report)
    assert result.code == inspection.code
    assert result.states == inspection.states
    if expected:
        assert result.serving.repository.identity == expected.identity
        assert result.serving.repository.candidates == (expected.focus,)
    else:
        assert not result.serving.repository.candidates
    assert "Selection-scoped repository evidence" in text_report(result)


def test_unrelated_ambiguity_does_not_downgrade_selected_serving(tmp_path):
    source = b"def predict(x: float) -> float:\n return x\n"
    path = tmp_path / "train.py"
    path.write_bytes(source)
    files = {
        "train.py": source,
        "unrelated.py": b"def duplicate(): pass\ndef duplicate(): pass\n",
    }
    catalog, graph, report = evidence(files)
    assert report.exit_code != 0
    result = enrich_serving(
        inspect_experiment(path), catalog=catalog, graph=graph, readiness=report
    )
    (candidate,) = result.serving.repository.candidates
    assert candidate.selected_state.value == "ready"
    assert candidate.interface_eligible
    expected = readiness_view(
        catalog,
        graph,
        report,
        ViewQuery(view="detail", capability_id=candidate.capability_id),
    )
    assert candidate == expected.focus


@pytest.mark.parametrize(
    "field,value",
    [("candidates", ()), ("module", "other"), ("interface_eligible", False)],
)
def test_reject_forged_repository_projection(tmp_path, field, value):
    path = write_source(tmp_path, "def predict(x: float): return x")
    catalog, graph, report = evidence({"train.py": path.read_bytes()})
    result = enrich_serving(
        inspect_experiment(path), catalog=catalog, graph=graph, readiness=report
    )
    repository = result.serving.repository
    if field == "candidates":
        repository = repository.model_copy(update={field: value})
    else:
        repository = repository.model_copy(
            update={
                "candidates": (
                    repository.candidates[0].model_copy(update={field: value}),
                )
            }
        )
    with pytest.raises(ValueError, match="repository_.*mismatch"):
        ExperimentInspection.model_validate(
            result.model_copy(
                update={
                    "serving": result.serving.model_copy(
                        update={"repository": repository}
                    )
                }
            )
        )


@pytest.mark.parametrize(
    "failure", ["missing", "uninspected", "stale", "module", "report"]
)
def test_refuse_wrong_repository_authority(tmp_path, failure):
    source = "def predict(x: float) -> float:\n return x\n"
    path = write_source(tmp_path, source)
    files = {"train.py": source.encode()}
    options = {}
    if failure == "missing":
        files = {"other.py": source.encode()}
    elif failure == "uninspected":
        files = {"train.py": b"x ="}
    elif failure == "stale":
        files = {"train.py": b"def predict(x: float): return x + 1\n"}
    elif failure == "module":
        options["module_name"] = "other"
    catalog, graph, report = evidence(files)
    if failure == "report":
        report = report.model_copy(update={"assessments": ()})
    with pytest.raises(ValueError):
        enrich_serving(
            inspect_experiment(path, **options),
            catalog=catalog,
            graph=graph,
            readiness=report,
        )
