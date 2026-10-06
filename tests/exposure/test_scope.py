"""#253: selection proof preserves the full audit and fails on required doubt."""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.exposure import (
    ExposurePolicy,
    ExposureRefused,
    plan_bytes,
    plan_exposure,
    refusal_report,
    validate_plan,
)
from apizr.exposure.scope import required_evidence
from apizr.graph import Graph, GraphPolicy, build_graph
from apizr.graph.model import Code as GraphCode
from apizr.graph.model import Diagnostic as GraphDiagnostic
from apizr.graph.model import RelationshipKind
from apizr.readiness.model import State
from apizr.repository import ScanPolicy, scan_sources
from apizr.repository_readiness import RepositoryReadinessPolicy, assess_repository

ROOT = "python:api:add"
API = b"def add(left: int, right: int) -> int:\n    return left + right\n"
AMBIGUOUS = b"from contextlib import contextmanager\n\n\n@contextmanager\ndef events():\n    yield 1\n"
UNRELATED = {
    "internal.py": AMBIGUOUS,
    "unused.py": b"from internal import events\n\n\ndef other():\n    return None\n",
}
CHAIN = {
    "api.py": b"from helper import normalize\ndef add(left:int,right:int)->int:\n return normalize(left)+right\n",
    "helper.py": b"from mathutil import adjust\ndef normalize(x:int)->int:\n return adjust(x)\n",
    "mathutil.py": b"def adjust(x:int)->int:\n return x\n",
}


def inputs(
    files=None,
    *,
    selected=(ROOT,),
    selection=None,
    graph_policy=None,
    scan_policy=None,
    readiness_policy=None,
    allow_conditional=False,
):
    files = {"api.py": API, **UNRELATED} if files is None else files
    catalog = scan_sources(files.items(), policy=scan_policy)
    retained = {
        path: content
        for path, content in files.items()
        if any(unit.path == path and unit.inspection for unit in catalog.sources)
    }
    graph = build_graph(catalog, retained, policy=graph_policy)
    readiness = assess_repository(catalog, graph, policy=readiness_policy)
    policy = ExposurePolicy.model_validate(
        {
            "selection": selection if selection is not None else {"include": selected},
            "interfaces": ["rest", "mcp"],
            "eligibility": {"allow_conditional": allow_conditional},
            "execution": {"allowed": ["local-process", "oci-container"]},
        }
    )
    return catalog, graph, readiness, policy


def accept(values):
    catalog, graph, readiness, policy = values
    return plan_exposure(catalog, graph, readiness, policy=policy)


def refuse(values):
    with pytest.raises(ExposureRefused) as raised:
        accept(values)
    return raised.value


@pytest.mark.parametrize("internal", [AMBIGUOUS, b"def events():\n yield 1\n"])
def test_issue_fixture_retains_full_audit_and_all_digest_bindings(internal):
    values = inputs({"api.py": API, **UNRELATED, "internal.py": internal})
    catalog, graph, readiness, policy = values
    before = [item.model_dump_json() for item in values]
    result = accept(values)
    assert result.capability_ids() == (ROOT,)
    assert graph.complete is (internal != AMBIGUOUS)
    if internal == AMBIGUOUS:
        assert [(d.code, d.path, d.line) for d in graph.diagnostics] == [
            (GraphCode.IMPORT, "unused.py", 1)
        ]
        assert (
            readiness.graph_diagnostics == graph.diagnostics
            and not readiness.graph_complete
        )
    assert [item.model_dump_json() for item in values] == before
    from apizr.graph.serialization import graph_digest
    from apizr.repository.serialization import catalog_digest
    from apizr.repository_readiness import report_digest

    assert result.repository_digest == catalog.repository_digest
    assert result.catalog_digest == catalog_digest(catalog)
    assert result.graph_digest == graph_digest(graph)
    assert result.repository_readiness_digest == report_digest(readiness)
    assert validate_plan(result, catalog, graph, readiness, policy=policy) == result


def test_unrelated_edits_change_full_identity_without_changing_eligibility():
    first = accept(inputs())
    second = accept(
        inputs(
            {
                "api.py": API,
                **UNRELATED,
                "scratch.py": b"raise RuntimeError('DO NOT RUN')\n",
            }
        )
    )
    assert first.capability_ids() == second.capability_ids() == (ROOT,)
    assert first.repository_digest != second.repository_digest
    assert first.catalog_digest != second.catalog_digest
    assert first.graph_digest != second.graph_digest
    assert first.repository_readiness_digest != second.repository_readiness_digest
    assert plan_bytes(first) != plan_bytes(second)


@pytest.mark.parametrize("selection", [{}, {"include": [ROOT], "exclude": [ROOT]}])
def test_empty_selection_has_no_path_scoped_execution_evidence(selection):
    assert accept(inputs(selection=selection)).capabilities == ()


@pytest.mark.parametrize(
    "policy",
    [
        GraphPolicy(max_ast_nodes=1),
        GraphPolicy(max_imports=1),
        GraphPolicy(max_relationships=1),
        GraphPolicy(max_calls=1),
    ],
)
@pytest.mark.parametrize("selected", [(), (ROOT,)])
def test_aggregate_graph_limit_blocks_even_empty_selection(policy, selected):
    values = inputs(
        {
            "api.py": API,
            "other.py": b"import api\nimport math\ndef f(): return api.add(1,2)+api.add(3,4)\n",
        },
        selected=selected,
        graph_policy=policy,
    )
    assert not values[1].complete
    error = refuse(values)
    assert any(
        d.code == "incomplete_evidence"
        and d.reason == "global"
        and d.evidence_code == GraphCode.LIMIT
        for d in error.diagnostics
    )


def test_opaque_incomplete_graph_is_global_without_inventing_clean_evidence():
    c, g, _, p = inputs({"api.py": API}, selected=())
    g = g.model_copy(update={"complete": False})
    r = assess_repository(c, g)
    error = refuse((c, g, r, p))
    assert error.diagnostics[0].reason == "global"


@pytest.mark.parametrize(
    "code", [GraphCode.INPUT, GraphCode.COLLISION, GraphCode.LIMIT]
)
def test_global_diagnostic_cannot_be_hidden_by_path(code):
    c, g, _, p = inputs({"api.py": API}, selected=())
    g = g.model_copy(
        update={
            "complete": False,
            "relationships": () if code == GraphCode.LIMIT else g.relationships,
            "diagnostics": (GraphDiagnostic(code=code, path="api.py"),),
        }
    )
    r = assess_repository(c, g)
    assert refuse((c, g, r, p)).diagnostics[0].reason == "global"


@pytest.mark.parametrize("broken", [b"not python !", b"\xff", b"x" * 100])
def test_locally_unavailable_unrelated_unit_can_stay_in_audit(broken):
    values = inputs(
        {"api.py": API, "broken.py": broken},
        scan_policy=ScanPolicy(max_file_bytes=len(API) + 5),
    )
    assert accept(values).capability_ids() == (ROOT,)
    assert values[0].exit_code == 1 and values[1].complete is False
    assert (
        values[0].diagnostics and values[2].catalog_diagnostics == values[0].diagnostics
    )


def test_required_unavailable_unit_is_refused():
    error = refuse(
        inputs({"api.py": b"import broken\n" + API, "broken.py": b"not python !"})
    )
    assert any(
        "python-module:broken" in d.dependency_path and d.source_path == "broken.py"
        for d in error.diagnostics
    )


def test_selected_unavailable_source_is_unknown_not_silently_dropped():
    values = inputs({"api.py": b"not python !"})
    assert any(
        d.code == "unknown_id" and d.capability_id == ROOT
        for d in refuse(values).diagnostics
    )


@pytest.mark.parametrize(
    "selection",
    [
        {"include": ["python:api:typo"]},
        {"exclude": ["python:api:typo"]},
        {"include": [ROOT], "exclude": ["python:api:typo"]},
    ],
)
def test_unknown_selection_and_exclusion_remain_errors(selection):
    assert any(
        d.code == "unknown_id" for d in refuse(inputs(selection=selection)).diagnostics
    )


def test_transitive_helpers_are_proven_execution_support_not_public_roots():
    values = inputs({**CHAIN, **UNRELATED})
    result = accept(values)
    scope = required_evidence(*values[:3], (ROOT,))
    assert result.capability_ids() == (ROOT,)
    assert {ROOT, "python:helper:normalize", "python:mathutil:adjust"}.issubset(
        scope.roots[ROOT].required_ids
    )
    assert (
        scope.roots[ROOT].issues == ()
        and result.capabilities[0].repository_readiness == State.READY
    )
    original = next(a for a in values[2].assessments if a.capability_id == ROOT)
    assert original.state == State.CONDITIONAL
    assert original.local_readiness.state == State.CONDITIONAL
    assert not original.local_readiness.can_generate_interface
    assert [
        r.code.value for r in original.local_readiness.dimensions.execution.reasons
    ] == ["APIZR-READY-015"]


def test_hard_interface_requirement_is_discharged_only_by_complete_selected_proof():
    assert accept(
        inputs(
            CHAIN, readiness_policy=RepositoryReadinessPolicy(require_interface=True)
        )
    ).capability_ids() == (ROOT,)


@pytest.mark.parametrize(
    "source",
    [
        b"from internal import events\ndef normalize(x:int)->int: return x\n",
        b"from internal import *\ndef normalize(x:int)->int: return x\n",
        b"import internal\ninternal=1\ndef normalize(x:int)->int: return x\n",
        b"def normalize(x:int)->int: return __import__('internal').events()\n",
        b"import importlib\ndef normalize(x:int)->int: return importlib.import_module('internal').events()\n",
        b"from ..internal import events\ndef normalize(x:int)->int: return x\n",
    ],
)
@pytest.mark.parametrize("allow", [False, True])
def test_required_ambiguity_dynamic_star_rebound_and_invalid_relative_block(
    source, allow
):
    values = inputs(
        {**CHAIN, "helper.py": source, "internal.py": AMBIGUOUS},
        allow_conditional=allow,
    )
    error = refuse(values)
    issues = [d for d in error.diagnostics if d.code == "incomplete_evidence"]
    assert issues and all(
        d.capability_id == ROOT and d.dependency_path[0] == ROOT for d in issues
    )
    assert any(d.source_path == "helper.py" for d in issues)
    assert "Required dependency path" in refusal_report(error, values[3])
    assert all("/Users" not in json.dumps(d.model_dump(mode="json")) for d in issues)


def test_required_import_is_followed_without_any_function_call_to_target():
    values = inputs(
        {
            **CHAIN,
            "helper.py": b"from config import SETTINGS\ndef normalize(x:int)->int: return x+SETTINGS\n",
            "config.py": b"SETTINGS=load_unknown()\n",
        }
    )
    error = refuse(values)
    assert any(
        "python-module:config" in d.dependency_path and d.reason == "initialization"
        for d in error.diagnostics
    )


@pytest.mark.parametrize(
    "initializer",
    [
        b"raise RuntimeError('DO NOT RUN')\n",
        b"from internal import events\n",
        b'"""no callable initialization evidence"""\n',
    ],
)
def test_required_package_initialization_blocks(initializer):
    files = {
        "api.py": b"from pkg.helper import normalize\n"
        + CHAIN["api.py"].split(b"\n", 1)[1],
        "pkg/__init__.py": initializer,
        "pkg/helper.py": b"def normalize(x:int)->int: return x\n",
        **UNRELATED,
    }
    error = refuse(inputs(files))
    assert any(
        "python-module:pkg" in d.dependency_path and d.source_path == "pkg/__init__.py"
        for d in error.diagnostics
    )


@pytest.mark.parametrize("initializer", [b"", b"def marker(): return None\n"])
def test_proven_package_and_unrelated_bad_package(initializer):
    files = {
        "pkg/__init__.py": initializer,
        "pkg/api.py": API,
        "badpkg/__init__.py": b"raise RuntimeError('DO NOT RUN')\n",
        **UNRELATED,
    }
    result = accept(inputs(files, selected=("python:pkg.api:add",)))
    assert result.capability_ids() == ("python:pkg.api:add",)


def test_namespace_parent_has_no_invented_initializer():
    assert accept(
        inputs({"pkg/api.py": API}, selected=("python:pkg.api:add",))
    ).capability_ids() == ("python:pkg.api:add",)


def test_cycles_terminate_and_keep_helpers_private():
    values = inputs(
        {
            "api.py": b"def add(left:int,right:int)->int: return one(left)+right\ndef one(x:int)->int: return two(x)\ndef two(x:int)->int: return one(x-1) if x else 0\n",
            **UNRELATED,
        }
    )
    assert accept(values).capability_ids() == (ROOT,)
    assert len(required_evidence(*values[:3], (ROOT,)).roots[ROOT].required_ids) == 4


@pytest.mark.parametrize(
    "module",
    [
        b"import helper\ndef add(left:int,right:int)->int: return helper.normalize(left)+right\n",
        b"def add(left:int,right:int)->int: return left+right\nimport helper\n",
    ],
)
def test_coherent_module_handle_cycles_are_not_rejected_just_for_cycling(module):
    files = {
        "api.py": module,
        "helper.py": b"import api\ndef normalize(x:int)->int: return x\n",
    }
    assert accept(inputs(files)).capability_ids() == (ROOT,)


def test_early_cyclic_callable_binding_is_unproven_initialization():
    files = {
        "api.py": b"from helper import normalize\ndef add(left:int,right:int)->int: return normalize(left)+right\n",
        "helper.py": b"from api import add\ndef normalize(x:int)->int: return x\n",
    }
    error = refuse(inputs(files))
    assert any(
        d.reason == "initialization"
        and d.source_path == "helper.py"
        and d.evidence_code.value == "APIZR-READY-015"
        for d in error.diagnostics
        if d.evidence_code
    )


def test_callable_references_are_required_even_without_direct_call_edge():
    files = {
        "api.py": b"def add(left:int,right:int)->int:\n callback=bad\n return callback(left)+right\ndef bad(x:int)->int:\n return __import__('unknown').run(x)\n"
    }
    values = inputs(files)
    assert any(
        edge.kind == RelationshipKind.REFERENCE for edge in values[1].relationships
    )
    assert any(
        "python:api:bad" in d.dependency_path for d in refuse(values).diagnostics
    )


def test_private_types_need_no_public_adapter_and_effects_are_not_propagated():
    files = {
        "api.py": b"from helper import private\ndef add(left:int,right:int)->int: return private(left)+right\n",
        "helper.py": b"def private(x:bytes)->int:\n open('file','w')\n return int(x)\n",
    }
    values = inputs(files)
    result = accept(values)
    root = next(a for a in values[2].assessments if a.capability_id == ROOT)
    assert result.capabilities[0].effects == root.effects
    assert result.capability_ids() == (ROOT,)
    assert (
        next(
            a
            for a in values[2].assessments
            if a.capability_id == "python:helper:private"
        ).local_readiness.state
        == State.UNSUPPORTED
    )


def test_multiple_roots_are_atomic_and_exclusions_do_not_remove_private_support():
    files = {
        "api.py": API + b"def blocked(): return __import__('unknown')\n",
        **UNRELATED,
    }
    error = refuse(inputs(files, selected=(ROOT, "python:api:blocked")))
    assert any(d.capability_id == "python:api:blocked" for d in error.diagnostics)
    assert accept(
        inputs(
            files,
            selection={"include_all_ready": True, "exclude": ["python:api:blocked"]},
        )
    ).capability_ids() == (ROOT,)
    result = accept(
        inputs(
            CHAIN,
            selection={
                "include": [ROOT, "python:helper:normalize"],
                "exclude": ["python:helper:normalize"],
            },
        )
    )
    assert result.capability_ids() == (ROOT,)


@pytest.mark.parametrize(
    "field",
    ["source", "target", "path", "line", "end_line", "column", "availability", "kind"],
)
def test_tampered_relationship_cannot_use_original_readiness(field):
    c, g, r, p = inputs(CHAIN)
    edge = next(edge for edge in g.relationships if edge.kind == RelationshipKind.CALL)
    changes = {
        "source": "python:mathutil:adjust",
        "target": "python:mathutil:adjust",
        "path": "mathutil.py",
        "line": 99,
        "end_line": 99,
        "column": 99,
        "availability": "conditional",
        "kind": "references_capability",
    }
    forged = g.model_copy(
        update={
            "relationships": tuple(
                edge.model_copy(update={field: changes[field]})
                if item == edge
                else item
                for item in g.relationships
            )
        }
    )
    with pytest.raises(ValueError):
        plan_exposure(c, forged, r, policy=p)


@pytest.mark.parametrize("field", ["line", "column", "availability", "source", "names"])
def test_tampered_import_cannot_use_original_readiness(field):
    c, g, r, p = inputs(CHAIN)
    declaration = g.imports[0]
    changes = {
        "line": 99,
        "column": 99,
        "availability": "conditional",
        "source": "python-module:mathutil",
        "names": tuple(
            name.model_copy(update={"resolution": "unresolved"})
            for name in declaration.names
        ),
    }
    forged = g.model_copy(
        update={
            "imports": (
                declaration.model_copy(update={field: changes[field]}),
                *g.imports[1:],
            )
        }
    )
    with pytest.raises(ValueError):
        plan_exposure(c, forged, r, policy=p)


def test_incoherent_import_locations_are_not_proof_even_with_rebound_report():
    c, g, _, p = inputs(CHAIN)
    edges = tuple(
        edge.model_copy(update={"column": edge.column + 1})
        if edge.kind == RelationshipKind.CAPABILITY
        else edge
        for edge in g.relationships
    )
    g = Graph.model_validate(
        g.model_copy(update={"relationships": edges}).model_dump(mode="json")
    )
    r = assess_repository(c, g)
    assert any(d.reason == "import" for d in refuse((c, g, r, p)).diagnostics)


def test_missing_containment_is_not_a_complete_selected_proof():
    c, g, _, p = inputs({"api.py": API})
    g = g.model_copy(update={"relationships": ()})
    r = assess_repository(c, g)
    assert any(d.reason == "binding" for d in refuse((c, g, r, p)).diagnostics)


def test_forged_success_plan_cannot_bypass_required_failure():
    good = accept(inputs())
    c, g, r, p = inputs({"api.py": b"from internal import events\n" + API, **UNRELATED})
    forged = good.model_copy(update={"repository_digest": c.repository_digest})
    with pytest.raises((ValueError, ExposureRefused)):
        validate_plan(forged, c, g, r, policy=p)


def test_scope_has_no_source_reanalysis_host_lookup_or_execution(monkeypatch):
    values = inputs(CHAIN)

    def forbidden(*args, **kwargs):
        raise AssertionError("static scope must consume retained evidence only")

    import importlib.util
    import socket

    import apizr.graph.builder as builder
    import apizr.inspection as inspection

    monkeypatch.setattr(ast, "parse", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(builder, "build_graph", forbidden)
    monkeypatch.setattr(builder, "analyze_repository", forbidden)
    monkeypatch.setattr(inspection, "inspect_source", forbidden)
    monkeypatch.setattr(importlib.util, "find_spec", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    assert accept(values).capability_ids() == (ROOT,)


def test_required_module_initialization_without_any_callable_is_not_guessed():
    values = inputs(
        {
            "api.py": b"import config\n" + API,
            "config.py": b"raise RuntimeError('UNRELATED ONLY IF NOT IMPORTED')\n",
        }
    )
    error = refuse(values)
    assert any(
        d.reason == "initialization" and d.source_path == "config.py"
        for d in error.diagnostics
    )


def test_global_catalog_limit_and_invalid_module_identity_block_empty_selection():
    values = inputs(
        {"api.py": API, "other.py": API},
        selected=(),
        scan_policy=ScanPolicy(max_source_files=1),
    )
    assert any(d.reason == "global" for d in refuse(values).diagnostics)
    values = inputs({"api.py": API, "9invalid.py": API}, selected=())
    assert any(d.reason == "global" for d in refuse(values).diagnostics)


def test_unrelated_symlink_warning_is_retained_without_becoming_a_global_error():
    from apizr.repository import ScanPolicy
    from apizr.repository.model import Code, Diagnostic
    from apizr.repository.scanner import SourceInput, assemble

    catalog = assemble(
        (SourceInput("api.py", API, len(API)),),
        ScanPolicy(),
        (Diagnostic(code=Code.SYMLINK, path="unused.py"),),
    )
    graph = build_graph(catalog, {"api.py": API})
    readiness = assess_repository(catalog, graph)
    policy = inputs({"api.py": API})[3]
    assert accept((catalog, graph, readiness, policy)).capability_ids() == (ROOT,)
    assert catalog.diagnostics[0].code == Code.SYMLINK


def test_root_binding_absent_from_graph_and_rebound_bindings_are_refused():
    assert refuse(inputs({"api.py": API + API})).diagnostics
    assert refuse(inputs({"api.py": API + b"add=1\n"})).diagnostics


def test_report_cannot_supply_missing_import_declarations_as_proof():
    c, g, _, p = inputs(CHAIN)
    g = g.model_copy(update={"imports": ()})
    r = assess_repository(c, g)
    assert any(
        d.evidence_code and d.evidence_code.value == "APIZR-READY-015"
        for d in refuse((c, g, r, p)).diagnostics
    )


def test_call_location_must_be_inside_its_bound_declaration():
    c, g, _, p = inputs(CHAIN)
    g = g.model_copy(
        update={
            "relationships": tuple(
                edge.model_copy(update={"line": 100, "end_line": 100})
                if edge.kind == RelationshipKind.CALL
                else edge
                for edge in g.relationships
            )
        }
    )
    r = assess_repository(c, g)
    assert any(d.reason == "binding" for d in refuse((c, g, r, p)).diagnostics)


def test_cyclic_callable_import_after_existing_definition_is_coherent():
    files = {
        "api.py": API + b"from helper import normalize\n",
        "helper.py": b"from api import add\ndef normalize(x:int)->int: return x\n",
    }
    assert accept(inputs(files)).capability_ids() == (ROOT,)


def test_unknown_scope_roots_are_not_caller_supplied_proof():
    values = inputs()
    with pytest.raises(ValueError, match="known readiness"):
        required_evidence(*values[:3], ("python:api:forged",))


def test_full_source_namespace_conflict_is_global_even_for_independent_root():
    files = {
        "api.py": API,
        "other.py": b"def f():return 1\n",
        "other/child.py": b"def f():return 2\n",
    }
    assert any(
        d.reason == "global" and d.evidence_code == GraphCode.COLLISION
        for d in refuse(inputs(files)).diagnostics
    )


def test_medium_transitive_repository_uses_bounded_iterative_scope():
    files = {
        f"helper{i}.py": f"from helper{i + 1} import normalize\ndef normalize(x:int)->int: return normalize(x)\n".encode()
        for i in range(150)
    }
    # Unique aliases avoid lexical name rebinding while retaining a long chain.
    files = {
        path: body.replace(
            b"import normalize\n", b"import normalize as next_value\n"
        ).replace(b"return normalize(x)", b"return next_value(x)")
        for path, body in files.items()
    }
    files["helper150.py"] = b"def normalize(x:int)->int:return x\n"
    files["api.py"] = CHAIN["api.py"].replace(b"from helper ", b"from helper0 ")
    values = inputs(files)
    assert accept(values).capability_ids() == (ROOT,)
    assert len(required_evidence(*values[:3], (ROOT,)).roots[ROOT].required_ids) == 304


@settings(max_examples=12, deadline=None)
@given(st.permutations(tuple(CHAIN)), st.booleans())
def test_input_order_and_unrelated_noise_do_not_change_public_selection(order, noise):
    files = {key: CHAIN[key] for key in order}
    if noise:
        files.update(UNRELATED)
    assert accept(inputs(files)).capability_ids() == (ROOT,)


@settings(max_examples=10, deadline=None)
@given(
    st.sampled_from(
        [
            b"raise RuntimeError('NO')\n",
            b"from internal import events\n",
            b"import unknown_external\n",
        ]
    )
)
def test_less_certain_required_evidence_never_becomes_more_eligible(prefix):
    assert accept(inputs(CHAIN)).capability_ids() == (ROOT,)
    assert refuse(
        inputs({**CHAIN, **UNRELATED, "mathutil.py": prefix + CHAIN["mathutil.py"]})
    ).diagnostics


def test_hash_seed_and_selection_order_have_identical_plan_bytes(tmp_path):
    script = """from apizr.exposure import ExposurePolicy,plan_bytes,plan_exposure
from apizr.repository import scan_sources
from apizr.graph import build_graph
from apizr.repository_readiness import assess_repository
files={'api.py':b'def add(left:int,right:int)->int: return left+right\\ndef second(x:int)->int: return x\\n','unused.py':b'raise RuntimeError(\"NO\")\\n'}
c=scan_sources(files.items());g=build_graph(c,files);r=assess_repository(c,g)
import os,sys
ids=['python:api:add','python:api:second']
if os.environ['PYTHONHASHSEED']=='29': ids.reverse()
p=ExposurePolicy.model_validate({'selection':{'include':ids},'interfaces':['rest','mcp'],'execution':{'allowed':['local-process']}})
sys.stdout.buffer.write(plan_bytes(plan_exposure(c,g,r,policy=p)))
"""
    outputs = []
    for seed in ("1", "29"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        outputs.append(
            subprocess.check_output(
                [sys.executable, "-c", script], env=env, cwd=tmp_path
            )
        )
    assert outputs[0] == outputs[1]
