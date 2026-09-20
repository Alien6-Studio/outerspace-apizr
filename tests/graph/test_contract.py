import ast
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from apizr.graph import (
    Code,
    Graph,
    GraphInputError,
    GraphPolicy,
    build_graph,
    graph_bytes,
    graph_digest,
    graph_repository,
    policy_bytes,
    policy_digest,
)
from apizr.graph.analysis import location
from apizr.graph.bindings import Site
from apizr.graph.model import (
    CapabilityNode,
    ExternalNode,
    Location,
    ModuleNode,
)
from apizr.graph.model import (
    RelationshipKind as K,
)
from apizr.repository import ScanPolicy, catalog_digest, scan_sources

FIXTURE = Path(__file__).parents[1] / "fixtures/graph/v1"


def test_reviewed_graph_and_schemas():
    result = graph_repository(
        FIXTURE / "project", scan_policy=ScanPolicy(source_roots=("src",))
    )
    g = result.graph
    assert graph_bytes(g) == (FIXTURE / "graph.json").read_bytes()
    assert Graph.model_validate_json(graph_bytes(g)) == g
    for model, value, name in [
        (Graph, g, "graph"),
        (GraphPolicy, g.graph_policy, "graph-policy"),
    ]:
        schema = model.model_json_schema()
        assert schema == json.loads(
            (
                Path(__file__).parents[2] / f"docs/specs/apizr-{name}-v1.schema.json"
            ).read_bytes()
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value.model_dump(mode="json"))
    assert g.catalog_digest == catalog_digest(result.catalog)
    assert (
        len(
            {
                g.catalog_digest.value,
                g.repository_digest.value,
                g.graph_policy_digest.value,
                graph_digest(g).value,
            }
        )
        == 4
    )
    assert g.capability_calls("python:shop.checkout:place_order") == (
        "python:shop.inventory:reserve",
        "python:shop.pricing:calculate",
    )
    assert {r.kind for r in g.relationships} == set(K)
    assert {Code.DYNAMIC, Code.STAR} <= {d.code for d in g.diagnostics}
    assert policy_bytes(GraphPolicy()) == policy_bytes(
        GraphPolicy.model_validate_json(policy_bytes(GraphPolicy()))
    )
    assert policy_digest(GraphPolicy()) == g.graph_policy_digest


def test_source_manifest_exactness_and_forged_catalog():
    files = {"a.py": b"def f(): return 1"}
    catalog = scan_sources(files.items())
    for sources in [
        {},
        {**files, "extra.py": b""},
        {"a.py": b"def f(): return 2"},
        {"a.py": bytearray(files["a.py"])},
    ]:
        with pytest.raises(GraphInputError, match="APIZR-GRAPH-001"):
            build_graph(catalog, sources)
    with pytest.raises(ValidationError):
        build_graph(catalog.model_copy(update={"capabilities": ()}), files)
    assert GraphInputError.code == Code.INPUT


def test_invalid_source_keeps_unique_module_but_is_not_reparsed(monkeypatch):
    catalog = scan_sources([("bad.py", b"invalid !"), ("good.py", b"pass")])
    original = ast.parse
    seen = []

    def parse(source, **kwargs):
        seen.append(source)
        return original(source, **kwargs)

    monkeypatch.setattr(ast, "parse", parse)
    g = build_graph(catalog, {"good.py": b"pass"})
    assert seen == [b"pass"]
    bad = next(n for n in g.nodes if n.module == "bad")
    assert bad.analyzed is False
    assert g.exit_code == 1
    assert Code.UNAVAILABLE in {d.code for d in g.diagnostics}


@pytest.mark.parametrize(
    "field,source",
    [
        ("max_ast_nodes", b"def f(): return 1"),
        ("max_calls", b"def f():\n f(); f()"),
        ("max_imports", b"import a\nimport b"),
        ("max_relationships", b"def f(): return 1\ndef g(): return f()"),
    ],
)
def test_aggregate_limits_discard_all_partial_relationships(field, source):
    files = {"first.py": b"def first(): return 1", "last.py": source}
    catalog = scan_sources(files.items())
    g = build_graph(catalog, files, policy=GraphPolicy(**{field: 1}))
    assert not g.complete
    assert not g.relationships and not g.imports
    assert all(n.kind != "external_module" for n in g.nodes)
    assert [d.code for d in g.diagnostics] == [Code.LIMIT]
    assert g.diagnostics[0].limit == field.removeprefix("max_")
    assert graph_bytes(g) == graph_bytes(
        build_graph(
            catalog,
            dict(reversed(list(files.items()))),
            policy=GraphPolicy(**{field: 1}),
        )
    )


def test_parser_limit_fail_closed_and_contradictory_parser_error(monkeypatch):
    files = {"a.py": b"def f(): pass"}
    c = scan_sources(files.items())

    def recursion(*args, **kwargs):
        raise RecursionError

    monkeypatch.setattr(ast, "parse", recursion)
    g = build_graph(c, files)
    assert not g.relationships and g.diagnostics[0].limit == "parser"

    def syntax(*args, **kwargs):
        raise SyntaxError("HOST_PRIVATE_DETAIL")

    monkeypatch.setattr(ast, "parse", syntax)
    with pytest.raises(GraphInputError) as error:
        build_graph(c, files)
    assert "HOST_PRIVATE_DETAIL" not in str(error.value)


@pytest.mark.parametrize(
    "field", ["max_ast_nodes", "max_relationships", "max_calls", "max_imports"]
)
def test_policy_bounds_and_no_ignored_options(field):
    for value in [0, -1, 10000000]:
        with pytest.raises(ValueError):
            GraphPolicy(**{field: value})
    with pytest.raises(ValueError):
        GraphPolicy(unrecognized=True)


def test_node_and_location_invariants():
    with pytest.raises(ValueError):
        ModuleNode(id="wrong", module="a", path="a.py", analyzed=True)
    with pytest.raises(ValueError):
        ExternalNode(id="python-external:bad", module="/usr/lib/bad")
    with pytest.raises(ValueError):
        ExternalNode(id="wrong", module="a")
    valid = {
        "id": "python:a:f",
        "module": "a",
        "name": "f",
        "path": "a.py",
        "readiness": "ready",
        "can_generate_interface": True,
        "execution": "sync",
    }
    for update in [
        {"id": "python:a:g"},
        {"name": "x.y"},
        {"path": "../a.py"},
        {"can_generate_interface": False},
    ]:
        with pytest.raises(ValueError):
            CapabilityNode(**(valid | update))
    valid_span = {
        "path": "a.py",
        "line": 1,
        "end_line": 1,
        "column": 0,
        "end_column": 2,
        "availability": "unconditional",
    }
    for update in [{"path": "/host/a.py"}, {"line": 2}, {"column": 4}]:
        with pytest.raises(ValueError):
            Location(**(valid_span | update))
    with pytest.raises(ValueError):
        location("a.py", Site(ast.Module(body=[], type_ignores=[]), "unconditional"))


def test_graph_rejects_forged_indexes_evidence_and_partial_limit_result():
    files = {
        "a.py": b"import b\nfrom b import f\ndef g(): return f()",
        "b.py": b"def f(): return 1",
    }
    g = build_graph(scan_sources(files.items()), files)
    data = g.model_dump(mode="json")

    def invalid(update):
        with pytest.raises(ValueError):
            Graph.model_validate(data | update)

    invalid({"nodes": [*data["nodes"], data["nodes"][0]]})
    invalid({"graph_policy_digest": {"algorithm": "sha256", "value": "0" * 64}})
    edge = data["relationships"][0]
    for change in [
        {"source": "missing"},
        {"target": "missing"},
        {"kind": "calls_capability"},
        {"path": "b.py"},
        {"resolution_evidence": "inferred"},
        {"target": "python:b:f"},
    ]:
        invalid({"relationships": [edge | change]})
    declaration = data["imports"][0]
    for change in [
        {"source": "missing"},
        {"path": "b.py"},
        {"scope": "capability_scope"},
        {"names": [{"name": "b", "resolution": "module", "target": "missing"}]},
    ]:
        invalid({"imports": [declaration | change]})
    invalid(
        {"diagnostics": [{"code": Code.LIMIT.value, "path": ".", "limit": "calls"}]}
    )
    invalid({"catalog_exit_code": 1})
    invalid(
        {
            "complete": False,
            "diagnostics": [{"code": Code.LIMIT.value, "path": ".", "limit": "calls"}],
        }
    )
    small_policy = GraphPolicy(max_relationships=1)
    invalid(
        {
            "graph_policy": small_policy.model_dump(mode="json"),
            "graph_policy_digest": policy_digest(small_policy).model_dump(mode="json"),
        }
    )
    forged = g.model_copy(
        update={
            "relationships": (
                g.relationships[0].model_copy(update={"target": "missing"}),
            )
        }
    )
    with pytest.raises(ValueError):
        graph_bytes(forged)


def test_import_resolution_evidence_is_unknown_until_target_established():
    from apizr.graph.model import ImportedName

    for values in [
        {"name": "f", "resolution": "capability"},
        {"name": "f", "resolution": "unresolved", "target": "python:a:f"},
        {"name": "f", "resolution": "capability", "target": "python:a:f"},
        {"name": "f", "alias": "a.b", "resolution": "unresolved"},
    ]:
        with pytest.raises(ValueError):
            ImportedName(**values)
    files = {"a.py": b"from unknown import f", "b.py": b"def f(): pass"}
    g = build_graph(scan_sources(files.items()), files)
    data = g.model_dump(mode="json")
    data["imports"][0]["names"][0]["target"] = "python:b:f"
    with pytest.raises(ValueError):
        Graph.model_validate(data)
