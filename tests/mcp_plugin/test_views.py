"""Canonical parity, exact navigation, evidence authority and bounded paging."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from apizr_mcp.model import (
    AnalysisOutput,
    Job,
    PlanArguments,
    ReadinessOutput,
    ViewArguments,
)
from apizr_mcp.scope import load_scope
from apizr_mcp.worker import calculate
from mcp_views_proof import fixture
from pydantic import ValidationError

from apizr.exposure.scope import required_evidence
from apizr.graph import GraphPolicy, analyze_repository, build_graph
from apizr.repository import ScanPolicy, scan_sources
from apizr.repository_readiness import assess_repository
from apizr.repository_views.model import Blockers, Page, ViewQuery
from apizr.repository_views.projection import action, analyze_view, readiness_view


@pytest.fixture(scope="module")
def large_project(tmp_path_factory):
    project, operator = fixture(tmp_path_factory.mktemp("views") / "project")
    from apizr.operator_policy import load_operator_policy

    scope = load_scope(project, load_operator_policy(operator))
    evidence = analyze_repository(scope.source(), operator_policy=scope.operator_policy)
    report = assess_repository(evidence.catalog, evidence.graph, policy=scope.readiness)
    return project, scope, evidence, report


def job(scope, operation="analyze", **arguments):
    model = PlanArguments if operation == "plan" else ViewArguments
    return Job(
        scope=scope,
        operation=operation,
        arguments=model.model_validate_json(json.dumps(arguments), strict=True),
    )


@pytest.mark.parametrize("operation", ["analyze", "readiness"])
def test_full_unchanged_and_strict_union(project, operation):
    scope = project[1]
    legacy = calculate(job(scope, operation))["value"]
    explicit = calculate(job(scope, operation, view="full"))["value"]
    assert explicit == legacy
    assert set(legacy) == (
        {"repository_digest", "catalog", "graph"}
        if operation == "analyze"
        else {"repository_digest", "report", "exit_code"}
    )
    model = AnalysisOutput if operation == "analyze" else ReadinessOutput
    assert (
        model.model_validate_json(json.dumps(legacy)).model_dump(mode="json") == legacy
    )
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps({**legacy, "view": "full"}))


@pytest.mark.parametrize(
    "arguments",
    [
        {"view": "unknown"},
        {"view": "summary", "module": "model"},
        {"module": "model"},
        {"view": "full", "offset": 0},
        {"view": "summary", "limit": 10},
        {"view": "detail"},
        {"view": "detail", "module": "model", "capability_id": "python:model:predict"},
        {"view": "detail", "module": "model", "offset": 1},
        {"view": "detail", "module": "model", "offset": -1},
        {"view": "detail", "module": "model", "limit": 0},
        {"view": "detail", "module": "model", "limit": 201},
        {"view": "detail", "module": "model", "limit": "10"},
        {"view": "detail", "module": "model", "offset": True},
        {"view": "detail", "capability_id": "predict"},
        {"view": "detail", "module": "../model"},
        {"view": "detail", "module": "x" * 513},
        {"view": "detail", "capability_id": "python:" + "x" * 1024 + ":f"},
        {"view": "summary", "root": "/"},
        {"view": "summary", "policy": {}},
        {"expected_repository_digest": "not-a-digest"},
    ],
)
def test_query_contract_rejects_incompatible_and_unbounded_inputs(arguments):
    with pytest.raises(ValidationError):
        ViewArguments.model_validate_json(json.dumps(arguments), strict=True)


def test_plan_navigation_contract_and_operation_separation(project):
    with pytest.raises(ValidationError):
        PlanArguments(offset=1)
    assert PlanArguments(offset=0, limit=200).limit == 200
    with pytest.raises(ValidationError):
        Job(scope=project[1], operation="plan", arguments=ViewArguments(view="summary"))
    with pytest.raises(ValidationError):
        Job(
            scope=project[1],
            operation="analyze",
            arguments=PlanArguments(policy=project[1].exposure),
        )


def test_summaries_are_small_views_of_full_identity(large_project, monkeypatch):
    _, scope, evidence, report = large_project
    from apizr_mcp import worker

    def forbidden(*args):
        raise AssertionError("Reduced mode must not materialize canonical full JSON")

    monkeypatch.setattr(worker, "catalog_bytes", forbidden)
    monkeypatch.setattr(worker, "graph_bytes", forbidden)
    monkeypatch.setattr(worker, "report_bytes", forbidden)
    analysis = calculate(job(scope, view="summary"))["value"]
    ready = calculate(job(scope, "readiness", view="summary"))["value"]
    assert analysis["view"] == ready["view"] == "summary"
    assert analysis["summary"]["sources"] == 69
    assert analysis["summary"]["capabilities"] == len(evidence.catalog.capabilities)
    assert (
        "catalog" not in analysis and "graph" not in analysis and "report" not in ready
    )
    assert ready["states"] == {s.value: n for s, n in report.counts.items()}
    assert ready["exit_code"] == report.exit_code == 1
    assert analysis["identity"]["catalog_digest"] == report.catalog_digest.model_dump(
        mode="json"
    )
    assert analysis["identity"]["graph_digest"] == report.graph_digest.model_dump(
        mode="json"
    )
    assert ready["principal_blockers"]["has_more"]
    assert len(ready["principal_blockers"]["shown"]) == 10
    for model, value in [(AnalysisOutput, analysis), (ReadinessOutput, ready)]:
        model.model_validate_json(json.dumps(value), strict=True)
        assert len(json.dumps(value).encode()) < 10000


def test_capability_slice_reuses_required_evidence_and_never_exposes_helpers(
    large_project,
):
    _, _, evidence, report = large_project
    root = "python:model:predict"
    query = ViewQuery(view="detail", capability_id=root, limit=200)
    view = readiness_view(evidence.catalog, evidence.graph, report, query)
    assert view.view == "detail" and view.focus.kind == "capability"
    authority = required_evidence(
        evidence.catalog, evidence.graph, report, (root,)
    ).roots[root]
    assert view.focus.selected_state == authority.state
    assert view.focus.interface_eligible == authority.interface_eligible
    assert view.focus.local_readiness.capability_id == root
    assert view.focus.local_readiness.dimensions.inputs.state.value == "ready"
    # All pages union the actual required slice, never a second resolver.
    records = list(view.records)
    while view.page.next_offset is not None:
        view = readiness_view(
            evidence.catalog,
            evidence.graph,
            report,
            ViewQuery(
                view="detail",
                capability_id=root,
                limit=200,
                offset=view.page.next_offset,
                expected_repository_digest=report.repository_digest.value,
            ),
        )
        records.extend(view.records)
    dependencies = [r for r in records if r.kind == "dependency"]
    assert {r.id for r in dependencies} == set(authority.required_ids) - {root}
    assert all(not r.exposed for r in dependencies)
    text = json.dumps([r.model_dump(mode="json") for r in records])
    assert "python:pipeline.step000:_step" in text
    assert "experiments.broken" not in text and "python:serving:predict" not in text


def test_module_view_uses_logical_module_and_paginated_records(large_project):
    _, _, evidence, report = large_project
    view = analyze_view(
        evidence.catalog,
        evidence.graph,
        ViewQuery(view="detail", module="serving"),
        report,
    )
    assert view.focus.kind == "module" and view.focus.source.path == "serving.py"
    assert view.focus.capability_count == 1
    assert any(
        r.kind == "capability" and r.capability_id == "python:serving:predict"
        for r in view.records
    )
    assert any(r.kind == "import" for r in view.records)
    assert "experiments.broken" not in view.model_dump_json()


@pytest.mark.parametrize("operation", ["analyze", "readiness"])
@pytest.mark.parametrize(
    "filter,code",
    [
        ({"capability_id": "python:model:missing"}, "unknown_capability"),
        ({"module": "missing"}, "unknown_module"),
    ],
)
def test_unknown_exact_identity_is_owned_refusal(
    large_project, operation, filter, code
):
    result = calculate(job(large_project[1], operation, view="detail", **filter))
    assert result == {"ok": False, "error": {"code": code, "diagnostics": []}}


@pytest.mark.parametrize("operation", ["analyze", "readiness"])
@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"view": "summary"},
        {"view": "detail", "capability_id": "python:model:predict"},
        {"view": "detail", "module": "model", "offset": 1},
    ],
)
def test_every_view_enforces_complete_repository_digest(
    large_project, operation, arguments
):
    assert (
        calculate(
            job(
                large_project[1],
                operation,
                expected_repository_digest="0" * 64,
                **arguments,
            )
        )
        .get("error", {})
        .get("code")
        == "repository_changed"
    )


def test_plan_refusal_localization_paging_and_drift(large_project):
    _, scope, _, report = large_project
    policy = {
        "selection": {"include": ["python:serving:predict"]},
        "interfaces": ["mcp", "rest"],
        "execution": {"allowed": ["direct"]},
    }
    complete = calculate(job(scope, "plan", policy=policy))["error"]
    assert complete["code"] == "exposure_refused" and "page" not in complete
    selected = [
        d for d in complete["diagnostics"] if d["evidence_code"] == "APIZR-GRAPH-002"
    ]
    assert selected and selected[0]["source_path"] == "config.py"
    assert selected[0]["line"] == 1 and selected[0]["action"] == "fix_import"
    assert selected[0]["dependency_path"][-1] == "python-module:config"
    union = []
    offset = 0
    while True:
        value = calculate(
            job(
                scope,
                "plan",
                policy=policy,
                offset=offset,
                limit=2,
                expected_repository_digest=report.repository_digest.value,
            )
        )["error"]
        union.extend(value["diagnostics"])
        assert value["diagnostic_count"] == len(complete["diagnostics"])
        if value["page"]["complete"]:
            break
        offset = value["page"]["next_offset"]
    assert union == complete["diagnostics"]
    assert (
        calculate(
            job(scope, "plan", policy=policy, expected_repository_digest="0" * 64)
        )["error"]["code"]
        == "repository_changed"
    )


@pytest.mark.parametrize(
    "arguments",
    [
        {
            "offset": 0,
            "limit": 2,
            "total": 4,
            "returned": 1,
            "next_offset": 2,
            "complete": False,
        },
        {
            "offset": 0,
            "limit": 2,
            "total": 4,
            "returned": 2,
            "next_offset": 3,
            "complete": False,
        },
        {
            "offset": 0,
            "limit": 2,
            "total": 4,
            "returned": 2,
            "next_offset": 2,
            "complete": True,
        },
    ],
)
def test_false_page_completeness_is_rejected(arguments):
    with pytest.raises(ValidationError):
        Page(**arguments)


def test_false_blocker_completeness_is_rejected():
    with pytest.raises(ValidationError):
        Blockers(total=1, shown=(), has_more=True)
    with pytest.raises(ValidationError):
        Blockers(total=0, shown=(), has_more=True)


@pytest.mark.parametrize(
    "arguments",
    [
        {"view": "full"},
        {"view": "summary"},
        {"view": "detail", "module": "calculator"},
        {"view": "detail", "capability_id": "python:calculator:add"},
        {"view": "detail", "module": "calculator", "offset": 1},
    ],
)
@pytest.mark.parametrize("operation", ["analyze", "readiness"])
def test_one_discovery_for_all_views(project, monkeypatch, arguments, operation):
    import apizr.graph.builder as builder

    original = builder.discover
    calls = []
    monkeypatch.setattr(
        builder, "discover", lambda *a, **kw: calls.append(1) or original(*a, **kw)
    )
    if arguments.get("offset"):
        arguments = {
            **arguments,
            "expected_repository_digest": calculate(job(project[1]))["value"][
                "repository_digest"
            ]["value"],
        }
        calls.clear()
    assert calculate(job(project[1], operation, **arguments))["ok"]
    assert calls == [1]


def canonical(files, *, scan=None, graph=None):
    catalog = scan_sources(files.items(), policy=scan)
    retained = {s.path: files[s.path] for s in catalog.sources if s.inspection}
    topology = build_graph(catalog, retained, policy=graph)
    return catalog, topology, assess_repository(catalog, topology)


def test_colliding_module_and_unparseable_source_remain_visible():
    catalog, graph, report = canonical(
        {
            "a/model.py": b"def f(): return 1",
            "b/model.py": b"def f(): return 2",
            "a/broken.py": b"def broken(",
        },
        scan=ScanPolicy(source_roots=("a", "b")),
    )
    view = readiness_view(
        catalog, graph, report, ViewQuery(view="detail", module="model")
    )
    assert view.focus.source_count == 2
    assert view.focus.source is None and view.focus.node is None
    assert view.principal_blockers.total == 4
    assert {d.origin for d in view.principal_blockers.shown} == {"catalog", "graph"}
    assert {r.source.path for r in view.records if r.kind == "source"} == {
        "a/model.py",
        "b/model.py",
    }
    broken = analyze_view(
        catalog, graph, ViewQuery(view="detail", module="broken"), report
    )
    assert not broken.focus.source.inspected
    assert any(
        r.kind == "diagnostic" and r.diagnostic.origin == "catalog"
        for r in broken.records
    )
    summary = analyze_view(catalog, graph, ViewQuery(view="summary"))
    assert summary.principal_blockers.total >= 3


def test_global_incomplete_evidence_cannot_be_hidden_by_tiny_page():
    catalog, graph, report = canonical(
        {"api.py": b"def f(x: int) -> int: return x"},
        graph=GraphPolicy(max_ast_nodes=1),
    )
    view = readiness_view(
        catalog,
        graph,
        report,
        ViewQuery(view="detail", capability_id="python:api:f", limit=1),
    )
    assert not view.focus.global_evidence_complete
    assert not view.focus.interface_eligible
    assert any(
        d.reason == "global" and d.action == "inspect_dependency"
        for d in view.principal_blockers.shown
    )
    assert view.page.returned == 1


def test_non_ir_declarations_and_local_refusal_stay_in_focus(large_project):
    _, _, evidence, report = large_project
    for module in (
        "experiments.ambiguous",
        "experiments.broken",
        "experiments.conditional",
    ):
        module_view = readiness_view(
            evidence.catalog,
            evidence.graph,
            report,
            ViewQuery(view="detail", module=module),
        )
        entries = [r for r in module_view.records if r.kind == "capability"]
        assert entries
        for entry in entries:
            view = readiness_view(
                evidence.catalog,
                evidence.graph,
                report,
                ViewQuery(view="detail", capability_id=entry.capability_id, limit=1),
            )
            assert view.focus.repository_state == entry.state
            assert view.principal_blockers.total
            assert not view.focus.interface_eligible


@pytest.mark.parametrize(
    "code,reason,expected",
    [
        ("unknown_id", None, "select_known_capability"),
        ("APIZR-READY-001", None, "fix_binding"),
        ("APIZR-READY-004", None, "fix_initialization"),
        ("interface", None, "resolve_interface_contract"),
        ("execution", None, "adjust_execution_requirements"),
        ("future", "diagnostic", "inspect_dependency"),
        ("future", None, None),
    ],
)
def test_action_contract_keeps_unknown_codes_neutral(code, reason, expected):
    assert action(code, reason) == expected


def test_projection_is_pure_and_rejects_unassessed_detail(large_project, monkeypatch):
    _, _, evidence, report = large_project
    import builtins
    import socket
    import typing

    def forbidden(*a, **kw):
        raise AssertionError("Projection must use only retained static artifacts")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(typing, "get_type_hints", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert (
        readiness_view(
            evidence.catalog,
            evidence.graph,
            report,
            ViewQuery(view="detail", capability_id="python:model:predict"),
        ).focus.capability_id
        == "python:model:predict"
    )
    with pytest.raises(ValueError, match="assessed"):
        analyze_view(
            evidence.catalog, evidence.graph, ViewQuery(view="detail", module="model")
        )
    with pytest.raises(ValueError, match="assessed"):
        analyze_view(evidence.catalog, evidence.graph, ViewQuery())
    with pytest.raises(ValueError, match="explicit"):
        readiness_view(evidence.catalog, evidence.graph, report, ViewQuery())


@pytest.mark.parametrize("operation", ["analyze", "readiness"])
@pytest.mark.parametrize(
    "arguments",
    [
        {"view": "summary"},
        {"view": "detail", "capability_id": "python:calculator:add"},
        {"view": "detail", "module": "calculator"},
    ],
)
def test_reduced_views_keep_operator_containment_and_never_execute_source(
    project, tmp_path, operation, arguments
):
    path, scope = project
    marker = tmp_path / "executed"
    source = path.parent / "src/calculator.py"
    source.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\ndef add(a: int, b: int=1) -> int:\n return a+b\n"
    )
    external = tmp_path / "external"
    external.mkdir()
    (external / "secret.py").write_text("def secret(): return 42")
    (source.parent / "escaped").symlink_to(external, target_is_directory=True)
    result = calculate(job(scope, operation, **arguments))
    assert result["ok"] and not marker.exists()
    assert "python:escaped.secret:secret" not in json.dumps(result)
    assert str(tmp_path) not in json.dumps(result)
    path.parent.rename(tmp_path / "old")
    path.parent.mkdir()
    assert (
        calculate(job(scope, operation, **arguments))["error"]["code"]
        == "scope_changed"
    )


def test_page_bytes_are_stable_across_hash_seed_relocation_and_creation_order(tmp_path):
    root = Path(__file__).resolve().parents[2]
    results = []
    for seed, reverse in [("0", False), ("1", True), ("321", False)]:
        project, operator = fixture(tmp_path / seed / "project", reverse=reverse)
        from apizr.operator_policy import load_operator_policy

        scope = load_scope(project, load_operator_policy(operator))
        envelope = job(
            scope,
            "readiness",
            view="detail",
            capability_id="python:model:predict",
            limit=7,
        )
        result = subprocess.run(
            [sys.executable, "-m", "apizr_mcp.worker"],
            input=envelope.model_dump_json(),
            capture_output=True,
            text=True,
            check=True,
            cwd=tmp_path,
            env={
                **os.environ,
                "PYTHONHASHSEED": seed,
                "PYTHONPATH": os.pathsep.join(
                    [str(root / "src"), str(root / "plugins/mcp/src")]
                ),
            },
        )
        results.append(result.stdout)
    assert results[0] == results[1] == results[2]
