"""Explicit selection, composed contracts and fail-closed adversarial evidence."""

import ast
import json
import shutil
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

from apizr.capabilities.model import Digest
from apizr.exposure import (
    ExposurePlan,
    ExposurePolicy,
    ExposureRefused,
    plan_bytes,
    plan_digest,
    plan_exposure,
    policy_bytes,
    policy_digest,
    refusal_report,
    text_report,
    validate_plan,
)
from apizr.graph import GraphPolicy, build_graph, graph_repository
from apizr.graph.model import Code, Diagnostic
from apizr.readiness import State
from apizr.repository import scan_sources
from apizr.repository_readiness import (
    RepositoryReadinessPolicy,
    assess_repository,
    report_digest,
)


def artifacts(files=None, *, graph_policy=None):
    files = files or {"a.py": b"def f(x: int): return x\n"}
    catalog = scan_sources(files.items())
    inspected = {s.path for s in catalog.sources if s.inspection}
    return catalog, build_graph(
        catalog, {p: b for p, b in files.items() if p in inspected}, policy=graph_policy
    )


ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "tests/fixtures/exposure/v1"


def policy(include=("python:a:f",), **updates):
    return ExposurePolicy.model_validate(
        {
            "selection": {"include": include},
            "interfaces": ["rest", "mcp"],
            "execution": {"allowed": ["local-process", "oci-container"]},
            **updates,
        }
    )


def plan(files=None, *, exposure=None, readiness_policy=None, graph_policy=None):
    c, g = artifacts(files, graph_policy=graph_policy)
    r = assess_repository(c, g, policy=readiness_policy)
    return plan_exposure(c, g, r, policy=exposure or policy())


def test_default_empty_and_explicit_all_ready_exclusions():
    files = {"a.py": b"def f(): return 1\ndef g(): return 2\ndef bad(): yield 3\n"}
    empty = plan(files, exposure=policy(selection={}))
    assert empty.capability_ids() == ()
    assert empty.observed_support_modules == empty.external_modules == ()
    selected = plan(
        files,
        exposure=policy(
            selection={
                "include_all_ready": True,
                "include": ["python:a:g"],
                "exclude": ["python:a:g"],
            }
        ),
    )
    assert selected.capability_ids() == ("python:a:f",)
    excluded_bad = plan(
        files,
        exposure=policy(
            selection={"include": ["python:a:bad"], "exclude": ["python:a:bad"]}
        ),
    )
    assert excluded_bad.capability_ids() == ()


@pytest.mark.parametrize(
    "selection",
    [
        {"include": ["python:a:typo"]},
        {"exclude": ["python:a:typo"]},
        {"include": ["python:a:typo"], "exclude": ["python:a:typo"]},
    ],
)
def test_unknown_ids_including_exclusions_block(selection):
    with pytest.raises(ExposureRefused) as error:
        plan(exposure=policy(selection=selection))
    assert error.value.diagnostics[0].code == "unknown_id"
    assert "Unknown requested" in refusal_report(error.value, policy())


@pytest.mark.parametrize(
    "source,state",
    [
        (b"def bad(x: Missing): return x\n", State.CONDITIONAL),
        (b"def bad(): yield 1\n", State.UNSUPPORTED),
        (b"def bad(): pass\ndef bad(): pass\n", State.AMBIGUOUS),
    ],
)
def test_refused_selection_never_returns_partial_plan(source, state):
    p = policy(("python:a:f", "python:a:bad"))
    with pytest.raises(ExposureRefused) as error:
        plan({"a.py": b"def f(): return 1\n" + source}, exposure=p)
    assert any(d.state == state for d in error.value.diagnostics)
    assert state.value.upper() in refusal_report(error.value, p)


def test_conditional_opt_in_preserves_effect_and_relationship_uncertainty():
    c, g = artifacts()
    # A validated graph may carry static uncertainty that local interface facts
    # do not contain. Exposure retains it; it never re-parses to repair evidence.
    g = g.model_copy(
        update={"diagnostics": (Diagnostic(code=Code.DYNAMIC, path="a.py", line=1),)}
    )
    rp = RepositoryReadinessPolicy.model_validate(
        {"effects": {"require_known": ["network"]}}
    )
    r = assess_repository(c, g, policy=rp)
    assert r.assessments[0].state == State.CONDITIONAL
    assert r.assessments[0].local_readiness.can_generate_interface
    with pytest.raises(ExposureRefused):
        plan_exposure(c, g, r, policy=policy())
    p = policy(eligibility={"allow_conditional": True})
    result = plan_exposure(c, g, r, policy=p)
    record = result.capabilities[0]
    assert record.repository_readiness == State.CONDITIONAL
    assert record.effects == r.assessments[0].effects
    assert record.relationships.diagnostics == g.diagnostics
    assert record.relationships.state == "partial"
    assert record.readiness_reasons == r.assessments[0].reasons
    assert "APIZR-GRAPH-005" in text_report(result, r)
    # include-all-ready deliberately ignores conditional even with opt-in.
    assert not plan_exposure(
        c,
        g,
        r,
        policy=policy(
            selection={"include_all_ready": True},
            eligibility={"allow_conditional": True},
        ),
    ).capabilities


def test_conditional_opt_in_cannot_override_shared_interface_contract():
    with pytest.raises(ExposureRefused) as error:
        plan(
            {"a.py": b"def f(x: Missing): return x"},
            exposure=policy(eligibility={"allow_conditional": True}),
        )
    assert {(d.code, d.interface) for d in error.value.diagnostics} == {
        ("interface", "mcp"),
        ("interface", "rest"),
    }
    assert "Shared interface contract" in refusal_report(error.value, policy())


def test_transport_eligibility_is_explicit_not_an_all_protocol_assumption(monkeypatch):
    import apizr.exposure.planner as planner

    monkeypatch.setattr(
        planner, "interface_compatibility", lambda _: {"rest": True, "mcp": False}
    )
    assert plan(exposure=policy(interfaces=["rest"])).interfaces == ("rest",)
    with pytest.raises(ExposureRefused) as error:
        plan()
    assert error.value.diagnostics[0].interface == "mcp"


@pytest.mark.parametrize(
    "required,expected",
    [
        ([], ("direct", "local-process", "oci-container")),
        (["wall_timeout"], ("local-process", "oci-container")),
        (["network_deny"], ("oci-container",)),
        (["memory_limit", "cpu_limit", "pid_limit"], ("oci-container",)),
        (["subprocess_deny"], ()),
    ],
)
def test_composed_execution_contracts_no_runtime_preference(required, expected):
    rp = RepositoryReadinessPolicy.model_validate(
        {"execution": {"modes": ["direct", "local-process", "oci-container"]}}
    )
    p = policy(
        execution={
            "allowed": ["oci-container", "direct", "local-process"],
            "require": required,
        }
    )
    if expected:
        result = plan(exposure=p, readiness_policy=rp)
        assert result.capabilities[0].compatible_execution_modes == expected
        assert len(result.compatible_with("oci-container")) == 1
    else:
        with pytest.raises(ExposureRefused) as error:
            plan(exposure=p, readiness_policy=rp)
        assert error.value.diagnostics[0].code == "execution"
        assert "subprocess_deny" in refusal_report(error.value, p)


def test_readiness_modes_are_authoritative_and_exposure_only_narrows():
    # Default readiness intentionally doesn't assess direct mode.
    with pytest.raises(ExposureRefused):
        plan(exposure=policy(execution={"allowed": ["direct"]}))
    rp = RepositoryReadinessPolicy.model_validate(
        {
            "execution": {
                "modes": ["local-process"],
                "require_controls": ["wall_timeout"],
            }
        }
    )
    result = plan(readiness_policy=rp)
    assert result.capabilities[0].compatible_execution_modes == ("local-process",)
    assert result.compatible_with("oci-container") == ()
    with pytest.raises(ExposureRefused):
        plan(
            exposure=policy(
                execution={"allowed": ["local-process"], "require": ["network_deny"]}
            )
        )


@pytest.mark.parametrize(
    "files,graph_policy",
    [
        ({"a.py": b"def f(): return 1", "broken.py": b"not python !"}, None),
        (None, GraphPolicy(max_ast_nodes=1)),
    ],
)
def test_globally_incomplete_evidence_blocks_even_empty_selection(files, graph_policy):
    with pytest.raises(ExposureRefused) as error:
        plan(files, exposure=policy(selection={}), graph_policy=graph_policy)
    assert error.value.diagnostics[0].code == "incomplete_evidence"
    assert "Complete repository evidence" in refusal_report(error.value, policy())


def test_dependency_relationships_are_evidence_never_transitive_exposure():
    files = {"a.py": b"def f(): return g()\ndef g(): return h()\ndef h(): yield 1\n"}
    result = plan(files)
    assert result.capability_ids() == ("python:a:f",)
    assert [
        (r.kind.value, r.target) for r in result.capabilities[0].relationships.direct
    ] == [("calls_capability", "python:a:g")]
    assert result.observed_support_modules == ("a",)
    assert len(result.for_interface("mcp")) == 1
    assert plan(files, exposure=policy(interfaces=["rest"])).for_interface("mcp") == ()


def test_evidence_identity_and_revalidation_reject_forged_snapshots():
    c, g = artifacts()
    r = assess_repository(c, g)
    p = policy()
    good = plan_exposure(c, g, r, policy=p)
    assert validate_plan(good, c, g, r, policy=p) == good
    wrong = Digest.of_bytes(b"wrong")
    for field in ("catalog_digest", "graph_digest", "repository_digest"):
        with pytest.raises(ValueError):
            plan_exposure(c, g, r.model_copy(update={field: wrong}), policy=p)
    for field in ("catalog_digest", "repository_digest"):
        with pytest.raises(ValueError):
            plan_exposure(c, g.model_copy(update={field: wrong}), r, policy=p)
    with pytest.raises(ValueError):
        plan_exposure(c, g, r.model_copy(update={"assessments": ()}), policy=p)
    with pytest.raises(ValueError):
        plan_exposure(c, g, r, policy=p.model_copy(update={"interfaces": ()}))
    with pytest.raises(ValueError):
        validate_plan(good.model_copy(update={"capabilities": ()}), c, g, r, policy=p)
    other = plan(
        {"a.py": b"def f(): return 1", "unselected.py": b"def other(): return 2"}
    )
    assert other.capability_ids() == good.capability_ids()
    for field in (
        "repository_digest",
        "catalog_digest",
        "graph_digest",
        "repository_readiness_digest",
    ):
        assert getattr(other, field) != getattr(good, field)
    assert plan_digest(other) != plan_digest(good)
    r2 = assess_repository(
        c, g, policy=RepositoryReadinessPolicy(require_interface=True)
    )
    assert report_digest(r2) != report_digest(r)
    assert plan_digest(plan_exposure(c, g, r2, policy=p)) != plan_digest(good)


@pytest.mark.parametrize(
    "update",
    [
        {"interfaces": ["grpc"]},
        {"interfaces": []},
        {"execution": {"allowed": []}},
        {"execution": {"allowed": ["unknown"]}},
        {"execution": {"allowed": ["direct"], "require": ["unknown"]}},
        {"selection": {"include": ["f"]}},
        {"selection": {"include": ["python:a:f.g"]}},
        {"selection": {"include": ["python:a:ｆ"]}},
        {"selection": {"include_all_ready": "yes"}},
        {"eligibility": {"allow_conditional": 1}},
        {"typo": 1},
    ],
)
def test_policy_has_no_fuzzy_identity_or_coercion_or_unknown_features(update):
    with pytest.raises(ValueError):
        policy(**update)


@given(
    st.permutations(["python:a:f", "python:a:g"]),
    st.permutations(["rest", "mcp"]),
    st.permutations(["oci-container", "local-process"]),
    st.permutations(["wall_timeout", "output_limit"]),
)
def test_set_order_independence(ids, interfaces, modes, controls):
    files = {"a.py": b"def f(): return 1\ndef g(): return 2"}
    a = policy(
        ids, interfaces=interfaces, execution={"allowed": modes, "require": controls}
    )
    b = policy(
        sorted(ids),
        interfaces=sorted(interfaces),
        execution={"allowed": sorted(modes), "require": sorted(controls)},
    )
    assert policy_bytes(a) == policy_bytes(b)
    assert plan_bytes(plan(files, exposure=a)) == plan_bytes(plan(files, exposure=b))


@given(st.sets(st.sampled_from(["local-process", "oci-container"]), min_size=1))
def test_stricter_execution_cannot_add_capabilities(modes):
    original = plan()
    narrowed = plan(exposure=policy(execution={"allowed": list(modes)}))
    assert set(narrowed.capability_ids()) <= set(original.capability_ids())
    assert set(narrowed.capabilities[0].compatible_execution_modes) == modes


@pytest.mark.parametrize(
    "update",
    [
        {"selection": {}},
        {"interfaces": ["mcp"]},
        {"execution": {"allowed": ["oci-container"]}},
        {"eligibility": {"allow_conditional": True}},
    ],
)
def test_semantic_policy_mutation_changes_policy_and_plan_digest(update):
    p = policy(**update)
    assert policy_digest(p) != policy_digest(policy())
    assert plan_digest(plan(exposure=p)) != plan_digest(plan())


def test_pure_api_does_not_scan_parse_read_files_or_probe(monkeypatch):
    c, g = artifacts()
    r = assess_repository(c, g)

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden operation")

    monkeypatch.setattr(ast, "parse", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    import apizr.execution.policy
    import apizr.graph

    monkeypatch.setattr(apizr.graph, "graph_repository", forbidden)
    monkeypatch.setattr(apizr.execution.policy, "local_capabilities", forbidden)
    assert plan_exposure(c, g, r, policy=policy()).capability_ids() == ("python:a:f",)


def test_golden_relocation_canonical_and_schemas(tmp_path):
    policy_value = ExposurePolicy.model_validate_json(
        (FIXTURE / "policy.json").read_bytes()
    )
    results = []
    for root in (FIXTURE / "project", tmp_path / "relocated"):
        if not root.exists():
            shutil.copytree(FIXTURE / "project", root)
        artifacts = graph_repository(root)
        report = assess_repository(artifacts.catalog, artifacts.graph)
        result = plan_exposure(
            artifacts.catalog, artifacts.graph, report, policy=policy_value
        )
        results.append(plan_bytes(result))
        assert str(root).encode() not in results[-1]
    assert results[0] == results[1] == (FIXTURE / "plan.json").read_bytes()
    assert result.capability_ids() == (
        "python:shop:availability",
        "python:shop:calculate",
    )
    assert "python:shop:helper" not in result.capability_ids()
    assert results[0].endswith(b"\n") and not results[0].endswith(b"\n\n")
    assert plan_bytes(ExposurePlan.model_validate_json(results[0])) == results[0]
    for model, value, name in (
        (ExposurePolicy, policy_value, "exposure-policy"),
        (ExposurePlan, result, "exposure-plan"),
    ):
        schema = json.loads(
            (ROOT / f"docs/specs/apizr-{name}-v1.schema.json").read_bytes()
        )
        assert schema == model.model_json_schema()
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value.model_dump(mode="json"))


def test_external_modules_are_lexical_and_not_classified_or_resolved():
    result = plan({"a.py": b"from typing import Any\ndef f(): return 1"})
    assert result.external_modules == ("typing",)
    assert result.observed_support_modules == ("a",)
    assert (
        result.capabilities[0].relationships.module_imports[0].kind
        == "imports_external_module"
    )
    assert "stdlib" not in plan_bytes(result).decode()


@pytest.mark.parametrize(
    "update",
    [
        {"module": "other"},
        {"capability_id": "f"},
        {"source_path": "/absolute.py"},
        {"repository_readiness": "unsupported"},
        {"compatible_interfaces": ("rest",)},
        {"compatible_execution_modes": ()},
    ],
)
def test_canonical_serialization_rejects_unchecked_invalid_records(update):
    result = plan()
    record = result.capabilities[0].model_copy(update=update)
    with pytest.raises(ValueError):
        plan_bytes(result.model_copy(update={"capabilities": (record,)}))


def test_plan_rejects_duplicate_records_and_inconsistent_interfaces_modules():
    result = plan()
    for update in [
        {"capabilities": (*result.capabilities, *result.capabilities)},
        {"interfaces": ("rest",)},
        {"observed_support_modules": ("ａ",)},
    ]:
        with pytest.raises(ValueError):
            plan_bytes(result.model_copy(update=update))


@given(
    st.sets(st.sampled_from(["python:a:f", "python:a:g", "python:a:h"])),
    st.sets(st.sampled_from(["python:a:f", "python:a:g", "python:a:h"])),
    st.booleans(),
)
def test_exclusion_precedence_for_every_selector_combination(
    included, excluded, all_ready
):
    files = {"a.py": b"def f(): return 1\ndef g(): return 2\ndef h(): return 3"}
    result = plan(
        files,
        exposure=policy(
            selection={
                "include": sorted(included),
                "exclude": sorted(excluded),
                "include_all_ready": all_ready,
            }
        ),
    )
    expected = (
        {"python:a:f", "python:a:g", "python:a:h"} if all_ready else included
    ) - excluded
    assert set(result.capability_ids()) == expected


@given(st.integers(min_value=2, max_value=12))
def test_longer_call_chains_never_expand_explicit_exposure(length):
    source = "\n".join(f"def f{i}(): return f{i + 1}()" for i in range(length - 1))
    source += f"\ndef f{length - 1}(): return 1\n"
    result = plan({"a.py": source.encode()}, exposure=policy(("python:a:f0",)))
    assert result.capability_ids() == ("python:a:f0",)
    assert [r.target for r in result.capabilities[0].relationships.direct] == [
        "python:a:f1"
    ]


def test_unselected_edits_and_graph_policy_changes_remain_bound():
    files = {"a.py": b"def f(): return 1", "other.py": b"def hidden(): return 2"}
    before = plan(files)
    edited = plan({**files, "other.py": b"def hidden(): return 3"})
    graph_changed = plan(files, graph_policy=GraphPolicy(max_calls=1))
    assert (
        before.capability_ids()
        == edited.capability_ids()
        == graph_changed.capability_ids()
    )
    assert before.catalog_digest != edited.catalog_digest
    assert before.graph_digest != graph_changed.graph_digest
    assert before.catalog_digest == graph_changed.catalog_digest
    assert len({plan_digest(p).value for p in (before, edited, graph_changed)}) == 3


def test_canonical_snapshot_sets_normalize_on_deserialization():
    c, g = artifacts(
        {
            "a.py": b"from typing import Any\ndef f(): return g() + h()\ndef g(): return 1\ndef h(): return 2"
        }
    )
    g = g.model_copy(
        update={
            "diagnostics": (
                Diagnostic(code=Code.DYNAMIC, path="a.py", line=2),
                Diagnostic(code=Code.REBOUND, path="a.py", line=2),
            )
        }
    )
    r = assess_repository(
        c,
        g,
        policy=RepositoryReadinessPolicy.model_validate(
            {"effects": {"require_known": ["network", "filesystem_read"]}}
        ),
    )
    original = plan_exposure(
        c, g, r, policy=policy(eligibility={"allow_conditional": True})
    )
    data = original.model_dump(mode="json")
    record = data["capabilities"][0]
    record["readiness_reasons"] = record["readiness_reasons"][::-1] * 2
    for field in ("direct", "module_imports", "imports", "diagnostics"):
        record["relationships"][field] = record["relationships"][field][::-1] * 2
    assert plan_bytes(ExposurePlan.model_validate(data)) == plan_bytes(original)
