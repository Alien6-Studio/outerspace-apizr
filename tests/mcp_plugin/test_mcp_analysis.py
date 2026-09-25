import json
import os

import pytest
from apizr_mcp.model import Job, PlanArguments
from apizr_mcp.scope import load_scope, open_root, policy_bytes
from apizr_mcp.worker import calculate
from pydantic import ValidationError

from apizr.compiler import assess_readiness, prepare_exposure
from apizr.exposure.serialization import plan_bytes
from apizr.graph import analyze_repository
from apizr.graph.serialization import graph_bytes
from apizr.repository.serialization import catalog_bytes
from apizr.repository_readiness.serialization import report_bytes


def job(scope, operation="analyze", **args):
    return Job(
        scope=scope,
        operation=operation,
        arguments=PlanArguments.model_validate_json(json.dumps(args), strict=True),
    )


def test_canonical_parity_single_analysis_and_no_source(project, monkeypatch):
    from apizr_mcp import worker

    path, scope = project
    real = worker.analyze_repository
    calls = []
    monkeypatch.setattr(
        worker, "analyze_repository", lambda *a, **k: calls.append(a) or real(*a, **k)
    )
    analysis = calculate(job(scope))["value"]
    evidence = analyze_repository(
        scope.root, scan_policy=scope.scan, graph_policy=scope.graph
    )
    assert analysis["catalog"] == json.loads(catalog_bytes(evidence.catalog))
    assert analysis["graph"] == json.loads(graph_bytes(evidence.graph))
    assert len(calls) == 1 and "sources" not in analysis
    ready = calculate(job(scope, "readiness"))["value"]
    expected = assess_readiness(
        scope.root,
        scan_policy=scope.scan,
        graph_policy=scope.graph,
        readiness_policy=scope.readiness,
    )
    assert ready["report"] == json.loads(report_bytes(expected))
    plan = calculate(job(scope, "plan"))["value"]
    expected = prepare_exposure(
        scope.root,
        scan_policy=scope.scan,
        graph_policy=scope.graph,
        readiness_policy=scope.readiness,
        policy=scope.exposure,
    )
    assert plan == json.loads(plan_bytes(expected.plan))


def test_readiness_nonzero_is_business_report_and_no_import(project):
    path, scope = project
    marker = path.parent / "executed"
    (path.parent / "src/calculator.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\ndef add(a: int, b: int=1):\n    return a+b\n"
    )
    result = calculate(job(scope, "readiness"))
    assert result["ok"] and result["value"]["exit_code"] == 1
    assert not marker.exists()


def test_frozen_policy_proposal_and_digest(project):
    path, scope = project
    before = calculate(job(scope))["value"]["repository_digest"]["value"]
    original = (path.parent / "policies/exposure.json").read_bytes()
    (path.parent / "policies/exposure.json").write_text("invalid")
    assert calculate(job(scope, "plan"))["ok"]
    source = path.parent / "src/calculator.py"
    source.write_text(source.read_text() + "\n# changed\n")
    assert (
        calculate(job(scope, expected_repository_digest=before))["error"]["code"]
        == "repository_changed"
    )
    assert calculate(job(scope))["ok"]
    (path.parent / "policies/exposure.json").write_bytes(original)


def test_missing_invalid_and_refused_policy(project):
    _, scope = project
    missing = scope.model_copy(update={"exposure": None})
    assert calculate(job(missing, "plan"))["error"]["code"] == "policy_required"
    proposed = scope.exposure.model_dump(mode="json")
    proposed["selection"]["include"] = ["python:calculator:missing"]
    refused = calculate(job(scope, "plan", policy=proposed))
    assert refused["error"]["code"] == "exposure_refused"
    assert refused["error"]["diagnostics"][0]["code"] == "unknown_id"
    assert calculate(
        job(missing, "plan", policy=scope.exposure.model_dump(mode="json"))
    )["ok"]
    with pytest.raises(ValidationError):
        job(scope, "plan", policy={"root": "/"})


def test_containment_replacement_and_links(project, tmp_path):
    path, scope = project
    external = tmp_path / "external"
    external.mkdir()
    (external / "secret.py").write_text("def secret(): return 42")
    (path.parent / "src/escaped").symlink_to(external, target_is_directory=True)
    (path.parent / "src/leak.py").symlink_to(external / "secret.py")
    result = calculate(job(scope))
    assert "python:leak:secret" not in json.dumps(result)
    assert "python:escaped.secret:secret" not in json.dumps(result)
    path.parent.rename(tmp_path / "old")
    path.parent.mkdir()
    assert calculate(job(scope))["error"]["code"] == "scope_changed"
    path.parent.rmdir()
    path.parent.symlink_to(external, target_is_directory=True)
    with pytest.raises(OSError):
        calculate(job(scope))


def test_root_guards_and_policy_file_bounds(tmp_path):
    with pytest.raises(ValueError):
        open_root("relative")
    file = tmp_path / "policy.json"
    file.write_bytes(b"x" * 65537)
    with pytest.raises(ValueError, match="policy_too_large"):
        policy_bytes(file)
    file.write_text('{"x":1,"x":2}')
    with pytest.raises(ValueError):
        policy_bytes(file)
    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(ValueError):
        policy_bytes(directory)
    with pytest.raises(ValueError):
        load_scope(directory)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(ValueError):
        load_scope(fifo)


def test_scope_missing_policy_default_and_symlink_root(project):
    path, _ = project
    path.write_text('schema_version = "apizr.project/v1"\nroot="src"\n')
    scope = load_scope(path)
    assert scope.exposure is None
    source = path.parent / "src"
    source.rename(path.parent / "original")
    source.symlink_to(path.parent / "original", target_is_directory=True)
    with pytest.raises(ValueError):
        load_scope(path)


@pytest.mark.parametrize("operation", ["analyze", "readiness", "plan"])
def test_each_tool_performs_one_discovery(project, monkeypatch, operation):
    import apizr.graph.builder as builder

    real = builder.discover
    calls = []
    monkeypatch.setattr(
        builder, "discover", lambda *a, **k: calls.append(a) or real(*a, **k)
    )
    assert calculate(job(project[1], operation))["ok"]
    assert len(calls) == 1
