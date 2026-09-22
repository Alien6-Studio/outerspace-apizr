"""Repository generation consumes exact evidence and shared invocation semantics."""

import ast
import json

import pytest

from apizr.capabilities.model import Digest
from apizr.exposure import ExposureRefused
from apizr.generators.mcp.planner import tool_name
from apizr.graph import analyze_repository
from apizr.interfaces.planner import plan as invocation_plan
from apizr.repository_interfaces.errors import BundleRefused
from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.planner import plan_repository_interface

from .conftest import evidence


@pytest.mark.parametrize("interface", ["rest", "mcp"])
def test_complete_universe_exact_selection_and_parity(inputs, interface):
    result = render_repository_bundle(*inputs, interface=interface)
    manifest = json.loads(result[f"apizr-repository-{interface}.json"])
    contract = json.loads(result["repository-interface.json"])
    assert len(manifest["sources"]) == 5
    assert len(contract["capabilities"]) == 3
    assert {c["public_name"] for c in contract["capabilities"]} == {
        "shop.api.run",
        "shop.pricing.run",
        "shop.inventory.available",
    }
    assert set(manifest["artifacts"]) == set(result) - {
        f"apizr-repository-{interface}.json"
    }
    for name, digest in manifest["artifacts"].items():
        assert Digest.of_bytes(result[name]).model_dump() == digest
    for capability in contract["capabilities"]:
        unit = next(u for u in inputs[0].sources if u.module == capability["module"])
        shared = invocation_plan(
            unit.inspection, inputs[-1][unit.path], select=[capability["capability_id"]]
        )
        assert capability["invocation"] == shared.capabilities[0].model_dump(
            mode="json"
        )
    assert result["source/shop/__init__.py"] == inputs[-1]["shop/__init__.py"]
    assert (
        b"helper"
        not in result["mcp-tools.json" if interface == "mcp" else "openapi.json"]
    )
    assert result == render_repository_bundle(
        *inputs[:-1], dict(reversed(list(inputs[-1].items()))), interface=interface
    )


@pytest.mark.parametrize("mutation", ["missing", "extra", "changed", "size"])
def test_exact_source_universe(inputs, mutation):
    sources = dict(inputs[-1])
    if mutation == "missing":
        sources.pop("shop/admin.py")
    elif mutation == "extra":
        sources["extra.py"] = b""
    elif mutation == "changed":
        sources["shop/admin.py"] = b"x" * len(sources["shop/admin.py"])
    else:
        sources["shop/admin.py"] += b" "
    with pytest.raises(ValueError, match="source"):
        render_repository_bundle(*inputs[:-1], sources, interface="rest")


@pytest.mark.parametrize("index", range(5))
def test_forged_evidence_refused(inputs, index):
    values = list(inputs)
    key = (
        "repository_digest",
        "catalog_digest",
        "graph_digest",
        "selection",
        "repository_digest",
    )[index]
    value = {"include": []} if index == 3 else Digest.of_bytes(b"forged")
    if index == 3:
        values[index] = values[index].model_copy(update={"interfaces": ("rest",)})
    else:
        values[index] = values[index].model_copy(update={key: value})
    with pytest.raises(ValueError):
        render_repository_bundle(*values, interface="rest")


def test_empty_wrong_transport_direct_refused():
    for inputs, interface, code in [
        (evidence(selected=()), "rest", "002"),
        (evidence(interfaces=("mcp",)), "rest", "001"),
        (evidence(modes=("oci-container",)), "rest", "003"),
    ]:
        with pytest.raises(BundleRefused, match=code):
            render_repository_bundle(*inputs, interface=interface)
    assert render_repository_bundle(
        *evidence(modes=("direct", "local-process", "oci-container")), interface="rest"
    )


def test_contradiction_and_namespaces():
    values = evidence(
        {"a.py": b"def f(): return 1\n", "a/b.py": b"def f(): return 2\n"},
        selected=("python:a.b:f",),
    )
    with pytest.raises(BundleRefused, match="004"):
        plan_repository_interface(*values, interface="rest")
    values = evidence({"a/b.py": b"def f(): return 2\n"}, selected=("python:a.b:f",))
    artifacts = render_repository_bundle(*values, interface="rest")
    assert "source/a/__init__.py" not in artifacts


def test_current_readiness_local_import_boundary():
    with pytest.raises(ExposureRefused):
        evidence(
            {
                "a.py": b"from b import helper\ndef run(): return helper()\n",
                "b.py": b"def helper(): return 2\n",
            },
            selected=("python:a:run",),
        )


def test_no_source_reanalysis(inputs, monkeypatch):
    import apizr.graph.builder
    import apizr.inspection
    import apizr.repository_readiness

    def forbidden(*args, **kwargs):
        raise AssertionError("Source reanalysis")

    parse = ast.parse

    def annotations_only(source, *args, **kwargs):
        assert kwargs.get("mode") == "eval"
        return parse(source, *args, **kwargs)

    monkeypatch.setattr(ast, "parse", annotations_only)
    monkeypatch.setattr(apizr.graph.builder, "build_graph", forbidden)
    monkeypatch.setattr(apizr.inspection, "inspect_source", forbidden)
    monkeypatch.setattr(apizr.repository_readiness, "assess_repository", forbidden)
    assert render_repository_bundle(*inputs, interface="mcp")


def test_hash_fallback_and_explicit_collision(monkeypatch):
    values = evidence({"café.py": b"def f(): return 1\n"}, selected=("python:café:f",))
    manifest = json.loads(
        render_repository_bundle(*values, interface="mcp")["apizr-repository-mcp.json"]
    )
    assert manifest["tools"][0]["tool_name"] == tool_name("python:café:f", "café.f")
    import apizr.repository_interfaces.generator as generator

    monkeypatch.setattr(generator, "tool_name", lambda *args: "collision")
    with pytest.raises(BundleRefused, match="005"):
        generator.render_repository_bundle(*evidence(), interface="mcp")


def test_one_discovery_retains_immutable_bytes(tmp_path, monkeypatch):
    import apizr.graph.builder as builder

    path = tmp_path / "a.py"
    original = b"def f(): return 1\n"
    path.write_bytes(original)
    discover = builder.discover
    calls = []

    def snapshot(*args):
        calls.append(1)
        result = discover(*args)
        path.write_bytes(b"raise RuntimeError('changed')")
        return result

    monkeypatch.setattr(builder, "discover", snapshot)
    result = analyze_repository(tmp_path)
    assert result.sources == {"a.py": original} and calls == [1]
    with pytest.raises(TypeError):
        result.sources["a.py"] = b"changed"


@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "identity",
        "sources",
        "source_paths",
        "empty",
        "duplicate",
        "missing_module",
    ],
)
def test_contract_internal_consistency(inputs, mutation):
    from apizr.repository_interfaces.model import RepositoryInterface

    value = plan_repository_interface(*inputs, interface="rest").model_dump(mode="json")
    if mutation == "path":
        value["sources"][0]["bundle_path"] = "source/wrong.py"
    elif mutation == "identity":
        value["capabilities"][0]["public_name"] = "wrong"
    elif mutation == "sources":
        value["sources"].append(value["sources"][0])
    elif mutation == "source_paths":
        value["sources"][1]["source_path"] = value["sources"][0]["source_path"]
    elif mutation == "empty":
        value["capabilities"] = []
    elif mutation == "duplicate":
        value["capabilities"].append(value["capabilities"][0])
    else:
        value["sources"] = [
            s
            for s in value["sources"]
            if s["module"] != value["capabilities"][0]["module"]
        ]
    with pytest.raises(ValueError):
        RepositoryInterface.model_validate(value)
