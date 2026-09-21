import ast
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

from apizr.capabilities import document_digest
from apizr.capabilities.model import Digest, Effects
from apizr.graph import Graph, GraphPolicy, build_graph, graph_digest
from apizr.graph.model import Code as GraphCode
from apizr.graph.model import Diagnostic as GraphDiagnostic
from apizr.inspection import Inspection, json_bytes
from apizr.readiness import State
from apizr.readiness.serialization import report_digest as local_digest
from apizr.repository import Catalog, catalog_digest, scan_sources
from apizr.repository.model import capability_entries
from apizr.repository_readiness import (
    Code,
    EffectRequirements,
    ExecutionRequirements,
    RelationshipRequirements,
    RepositoryReadinessPolicy,
    RepositoryReadinessReport,
    assess_repository,
    execution_compatibility,
    policy_bytes,
    policy_digest,
    report_bytes,
    report_digest,
    validate_report,
)
from apizr.repository_readiness.model import Dependency, Reason
from apizr.repository_readiness.reporting import text_report

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "tests/fixtures/repository_readiness/v1"


def artifacts(files=None, *, effects=None, graph_policy=None):
    files = files or {"a.py": b"def f(x: int): return x\n"}
    catalog = scan_sources(files.items())
    if effects:
        sources = []
        for source in catalog.sources:
            inspection = source.inspection
            if inspection:
                data = inspection.capability_ir.model_dump(mode="json")
                for c in data["capabilities"]:
                    if c["id"] in effects:
                        c["effects"].update(effects[c["id"]])
                ir = type(inspection.capability_ir).model_validate(data)
                readiness = inspection.readiness.model_copy(
                    update={"ir_digest": document_digest(ir)}
                )
                inspection = Inspection(
                    capability_ir=ir,
                    ir_digest=document_digest(ir),
                    readiness=readiness,
                    readiness_digest=local_digest(readiness),
                )
                source = source.model_copy(
                    update={
                        "inspection": inspection,
                        "inspection_digest": Digest.of_bytes(json_bytes(inspection)),
                    }
                )
            sources.append(source)
        catalog = Catalog.model_validate(
            catalog.model_copy(
                update={
                    "sources": tuple(sources),
                    "capabilities": capability_entries(tuple(sources)),
                }
            ).model_dump(mode="json")
        )
    inspected = {s.path for s in catalog.sources if s.inspection}
    return catalog, build_graph(
        catalog, {p: b for p, b in files.items() if p in inspected}, policy=graph_policy
    )


def assess(files=None, *, effects=None, policy=None, graph_policy=None):
    c, g = artifacts(files, effects=effects, graph_policy=graph_policy)
    return assess_repository(c, g, policy=policy)


def test_all_declarations_preserve_authoritative_readiness():
    report = assess(
        {
            "a.py": b"def ready(x: int): return x\ndef generator(): yield 1\ndef conditional(x: Missing): pass\ndef duplicate(): pass\ndef duplicate(): pass\n",
        }
    )
    by_name = {a.local_readiness.source.symbol: a for a in report.assessments}
    assert len(by_name) == 4
    assert {a.state for a in report.assessments} == set(State)
    rejected = by_name["duplicate"]
    assert not rejected.in_catalog and not rejected.local_readiness.in_ir
    assert rejected.capability_id == "python:a:duplicate"
    assert rejected.relationships.state == "unavailable"
    assert rejected.effects == Effects()
    assert Code.CATALOG in {r.code for r in rejected.reasons}
    assert report.counts == dict.fromkeys(State, 1)
    text = text_report(report)
    assert "APIZR-READY-009" in text and "not a runtime guarantee" in text
    assert "APIZR-REPOREADY-008" in text and report.exit_code == 1


@pytest.mark.parametrize("name", list(Effects.model_fields))
@pytest.mark.parametrize("requirement", ["require_known", "require_false"])
@pytest.mark.parametrize("value", ["true", "false", "unknown"])
def test_effect_truth_table(name, requirement, value):
    policy = RepositoryReadinessPolicy(
        effects=EffectRequirements(**{requirement: (name,)})
    )
    fact = {"value": value, "evidence": "unknown" if value == "unknown" else "declared"}
    report = assess(effects={"python:a:f": {name: fact}}, policy=policy)
    a = report.assessments[0]
    expected = (
        State.CONDITIONAL
        if value == "unknown"
        else State.UNSUPPORTED
        if value == "true" and requirement == "require_false"
        else State.READY
    )
    assert a.state == expected
    assert getattr(a.effects, name).model_dump(mode="json") == fact
    assert (a.reasons[0].effect if a.reasons else None) == (
        name if expected != State.READY else None
    )


def test_no_callee_effect_or_state_propagation_or_transitive_closure():
    files = {
        "a.py": b"def caller(): return target()\ndef target(): return last()\ndef last(): yield 1\n"
    }
    policy = RepositoryReadinessPolicy(
        effects=EffectRequirements(require_false=("network",))
    )
    report = assess(
        files,
        policy=policy,
        effects={
            "python:a:caller": {"network": {"value": "false", "evidence": "declared"}},
            "python:a:target": {"network": {"value": "true", "evidence": "declared"}},
        },
    )
    by_id = {a.capability_id: a for a in report.assessments}
    caller = by_id["python:a:caller"]
    assert caller.state == State.READY
    assert caller.effects.network.value == "false"
    assert [d.capability_id for d in caller.relationships.dependencies] == [
        "python:a:target"
    ]
    assert caller.relationships.dependencies[0].effects.network.value == "true"
    assert by_id["python:a:target"].state == State.UNSUPPORTED
    assert (
        by_id["python:a:target"].relationships.dependencies[0].local_readiness.state
        == State.UNSUPPORTED
    )


@pytest.mark.parametrize(
    "control,compatible",
    [
        ("wall_timeout", {"local-process", "oci-container"}),
        ("input_limit", {"local-process", "oci-container"}),
        ("output_limit", {"local-process", "oci-container"}),
        ("environment", {"local-process", "oci-container"}),
        ("working_directory", {"local-process", "oci-container"}),
        ("network_deny", {"oci-container"}),
        ("filesystem_sandbox", {"oci-container"}),
        ("subprocess_deny", set()),
    ],
)
def test_declared_execution_control_matrix(control, compatible):
    report = assess(
        policy=RepositoryReadinessPolicy(
            execution=ExecutionRequirements(require_controls=(control,))
        )
    )
    assert {m.mode for m in report.execution if m.compatible} == compatible
    assert all(m.runtime_availability == "not_assessed" for m in report.execution)
    assert report.assessments[0].state == (
        State.READY if compatible else State.UNSUPPORTED
    )


def test_local_only_controls_and_interface_hard_requirement():
    report = assess(
        policy=RepositoryReadinessPolicy(
            execution=ExecutionRequirements(
                modes=("local-process",),
                require_controls=("network_deny", "filesystem_sandbox"),
            )
        )
    )
    assert report.assessments[0].state == State.UNSUPPORTED
    assert report.execution[0].missing_controls == (
        "filesystem_sandbox",
        "network_deny",
    )
    files = {"a.py": b"def f(x: Missing): return x"}
    assert assess(files).assessments[0].state == State.CONDITIONAL
    assert (
        assess(files, policy=RepositoryReadinessPolicy(require_interface=True))
        .assessments[0]
        .state
        == State.UNSUPPORTED
    )


@pytest.mark.parametrize(
    "body,code",
    [
        (b"from missing import *\ndef f(): return 1", GraphCode.STAR),
        (b'def f():\n return __import__("missing")', GraphCode.DYNAMIC),
        (b"import other\nother = 1\ndef f(): return other()", GraphCode.REBOUND),
    ],
)
def test_relationship_uncertainty(body, code):
    report = assess({"a.py": body})
    a = report.assessments[0]
    assert a.relationships.state == "partial"
    assert code in {d.code for d in a.relationships.diagnostics}
    assert Code.RELATIONSHIP in {r.code for r in a.reasons}
    relaxed = assess(
        {"a.py": body},
        policy=RepositoryReadinessPolicy(
            relationships=RelationshipRequirements(require_resolved=False)
        ),
    )
    assert Code.RELATIONSHIP not in {r.code for r in relaxed.assessments[0].reasons}


def test_diagnostic_scope_is_capability_then_module_never_unrelated():
    report = assess(
        {
            "a.py": b'def uncertain():\n return __import__("x")\ndef other(): return 1\n',
            "b.py": b"from missing import *\ndef f(): return 1\n",
            "c.py": b"def f(): return 1\n",
        }
    )
    by_id = {a.capability_id: a for a in report.assessments}
    assert by_id["python:a:uncertain"].relationships.state == "partial"
    assert by_id["python:a:other"].relationships.state == "resolved"
    assert by_id["python:b:f"].relationships.state == "partial"
    assert by_id["python:c:f"].state == State.READY


def test_resolved_external_imports_and_module_import_context():
    report = assess(
        {
            "a.py": b"import external_package\nfrom b import f\ndef g(): return f\n",
            "b.py": b"def f(): return 1\n",
        }
    )
    a = report.assessments[0]
    assert a.relationships.state == "resolved"
    assert {e.kind.value for e in a.relationships.module_imports} == {
        "imports_external_module",
        "imports_capability",
        "imports_module",
    }
    assert a.relationships.direct[0].kind.value == "references_capability"
    assert [d.capability_id for d in a.relationships.dependencies] == ["python:b:f"]
    # Existing local dependency uncertainty stays authoritative.
    assert a.local_readiness.state == a.state == State.CONDITIONAL


def test_graph_limits_are_unavailable_even_for_otherwise_ready_declarations():
    report = assess(graph_policy=GraphPolicy(max_ast_nodes=1))
    assert report.assessments[0].relationships.state == "unavailable"
    assert report.assessments[0].state == State.CONDITIONAL
    assert report.graph_complete is False
    assert Code.GRAPH in {r.code for r in report.assessments[0].reasons}


@pytest.mark.parametrize("code", [GraphCode.IMPORT, GraphCode.COLLISION])
def test_graph_identity_ambiguity_wins_over_hard_failures(code):
    c, g = artifacts()
    g = g.model_copy(
        update={
            "complete": False,
            "diagnostics": (GraphDiagnostic(code=code, path="a.py", line=1),),
        }
    )
    policy = RepositoryReadinessPolicy(
        execution=ExecutionRequirements(require_controls=("subprocess_deny",))
    )
    a = assess_repository(c, g, policy=policy).assessments[0]
    assert a.state == State.AMBIGUOUS
    assert Code.IDENTITY in {r.code for r in a.reasons}


def test_empty_and_failed_sources_are_not_silently_claimed_ready():
    assert assess({"a.py": b"pass"}).counts == dict.fromkeys(State, 0)
    report = assess({"a.py": b"invalid !"})
    assert (
        not report.assessments and report.catalog_diagnostics and report.exit_code == 1
    )


def test_pure_boundary_no_scan_parse_readiness_or_execution(monkeypatch):
    c, g = artifacts()

    def forbidden(*args, **kwargs):
        raise AssertionError("Forbidden operation")

    monkeypatch.setattr(ast, "parse", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    with (
        patch("apizr.repository.scanner.scan_sources", forbidden),
        patch("apizr.readiness.assess", forbidden),
        patch("apizr.execution.execute", forbidden),
        patch("apizr.execution.policy.local_capabilities", forbidden),
    ):
        assert assess_repository(c, g).assessments[0].state == State.READY


@pytest.mark.filterwarnings("ignore:Pydantic serializer warnings:UserWarning")
def test_linkage_and_unchecked_model_copies_rejected():
    c, g = artifacts()
    zero = Digest.of_bytes(b"wrong")
    for bad_catalog in [
        c.model_copy(update={"capabilities": ()}),
        c.model_construct(**(c.model_dump() | {"repository_digest": zero})),
    ]:
        with pytest.raises(ValueError):
            assess_repository(bad_catalog, g)
    for update in [
        {"catalog_digest": zero},
        {"repository_digest": zero},
        {"graph_policy_digest": zero},
        {"nodes": ()},
        {"catalog_exit_code": 1, "complete": False},
        {
            "relationships": (
                g.relationships[0].model_copy(update={"target": "missing"}),
            )
        },
        {
            "nodes": tuple(
                n.model_copy(update={"execution": "async"})
                if n.kind == "capability"
                else n
                for n in g.nodes
            )
        },
        {
            "nodes": tuple(
                n.model_copy(update={"path": "other.py"}) if n.kind == "module" else n
                for n in g.nodes
            ),
            "relationships": (),
        },
    ]:
        with pytest.raises(ValueError):
            assess_repository(c, g.model_copy(update=update))
    with pytest.raises(ValueError):
        assess_repository(
            c,
            g,
            policy=RepositoryReadinessPolicy.model_construct(require_interface="yes"),
        )


def test_report_verification_checks_evidence_not_only_digests():
    c, g = artifacts()
    report = assess_repository(c, g)
    assert validate_report(report, c, g) == report
    a = report.assessments[0]
    for update in [
        {"policy_digest": Digest.of_bytes(b"wrong")},
        {"execution": ()},
        {"assessments": (a, a)},
        {"assessments": (a.model_copy(update={"state": State.AMBIGUOUS}),)},
        {"assessments": (a.model_copy(update={"in_catalog": False}),)},
        {"assessments": (a.model_copy(update={"capability_id": "wrong"}),)},
    ]:
        with pytest.raises(ValueError):
            report_bytes(report.model_copy(update=update))
    forged = report.model_copy(update={"assessments": ()})
    with pytest.raises(ValueError, match="bound artifacts"):
        validate_report(forged, c, g)
    with pytest.raises(ValueError):
        Reason(code=Code.EFFECT_UNKNOWN)
    with pytest.raises(ValueError):
        Dependency(
            capability_id="wrong", local_readiness=a.local_readiness, effects=a.effects
        )


def test_policy_validation_canonicalization_and_domain_separated_digests():
    a = RepositoryReadinessPolicy(
        effects=EffectRequirements(require_false=("secrets", "network", "secrets"))
    )
    b = RepositoryReadinessPolicy(
        effects=EffectRequirements(require_false=("network", "secrets"))
    )
    assert policy_bytes(a) == policy_bytes(b)
    for value in [
        {"typo": True},
        {"effects": {"require_known": ["typo"]}},
        {"execution": {"modes": []}},
        {"execution": {"require_controls": ["typo"]}},
        {"require_interface": "true"},
        {"relationships": {"require_resolved": 1}},
    ]:
        with pytest.raises(ValueError):
            RepositoryReadinessPolicy.model_validate(value)
    c, g = artifacts()
    report = assess_repository(c, g)
    assert (
        len(
            {
                c.repository_digest.value,
                catalog_digest(c).value,
                graph_digest(g).value,
                policy_digest(report.policy).value,
                report_digest(report).value,
            }
        )
        == 5
    )
    assert report_bytes(report) == report_bytes(
        RepositoryReadinessReport.model_validate_json(report_bytes(report))
    )
    assert report_digest(report) != report_digest(assess_repository(c, g, policy=a))


@given(
    st.permutations(
        [
            ("a.py", b"def f(): return 1"),
            ("b.py", b"def g(): return 2"),
            ("c.py", b"def h(): return 3"),
        ]
    )
)
def test_artifact_order_does_not_change_report(files):
    assert report_bytes(assess(dict(files))) == report_bytes(
        assess(dict(sorted(files)))
    )


def test_reviewed_contracts_and_golden():
    c = Catalog.model_validate_json((FIXTURE / "catalog.json").read_bytes())
    g = Graph.model_validate_json((FIXTURE / "graph.json").read_bytes())
    policy = RepositoryReadinessPolicy.model_validate_json(
        (FIXTURE / "policy.json").read_bytes()
    )
    report = assess_repository(c, g, policy=policy)
    assert report_bytes(report) == (FIXTURE / "report.json").read_bytes()
    for model, value, name in [
        (RepositoryReadinessPolicy, policy, "repository-readiness-policy"),
        (RepositoryReadinessReport, report, "repository-readiness"),
    ]:
        schema = json.loads(
            (ROOT / f"docs/specs/apizr-{name}-v1.schema.json").read_bytes()
        )
        assert schema == model.model_json_schema()
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value.model_dump(mode="json"))


def test_execution_contracts_agree_with_existing_planners():
    from apizr.execution.policy import (
        BackendCapabilities,
        ExecutionPolicy,
        PolicyRefused,
        check_controls,
    )
    from apizr.oci.model import ExecutionPolicyV2
    from apizr.oci.planner import check_controls as oci_check

    with pytest.raises(PolicyRefused):
        check_controls(
            ExecutionPolicy.model_validate({"subprocess": {"mode": "deny"}}),
            BackendCapabilities(available=True),
        )
    with pytest.raises(PolicyRefused):
        oci_check(ExecutionPolicyV2.model_validate({"subprocess": {"mode": "deny"}}))
    assert not any(
        m.compatible
        for m in execution_compatibility(
            ExecutionRequirements(require_controls=("subprocess_deny",))
        )
    )
