"""Trusted runtime integration is separate from non-executing generation."""

import importlib
import json
import sys
import types

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp import Client

from apizr.interfaces.runtime import IntegrityError
from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.mcp_runtime import create_server, result_value
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_interfaces.rest_runtime import create_app
from apizr.repository_interfaces.runtime import RepositoryLoader, digest

from .conftest import evidence


@pytest.fixture(autouse=True)
def clean_imports():
    before = list(sys.meta_path)
    yield
    for finder in list(sys.meta_path):
        if isinstance(finder, RepositoryLoader) and finder not in before:
            finder.close()


def bundle(root, inputs, interface):
    artifacts = render_repository_bundle(*inputs, interface=interface)
    write_bundle(root, artifacts)
    return artifacts


def test_rest_sync_async_helpers_namespace_and_public_surface(tmp_path, inputs):
    bundle(tmp_path, inputs, "rest")
    app = create_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.post("/capabilities/shop.api.run", json={}).json() == 7
        assert client.post("/capabilities/shop.pricing.run", json={"x": 4}).json() == 5
        assert (
            client.post("/capabilities/shop.inventory.available", json={}).json()
            is True
        )
        assert client.post("/capabilities/shop.api.helper", json={}).status_code == 404
        assert (
            client.post("/capabilities/shop.api.run", json={"x": "bad"}).status_code
            == 422
        )
        assert (
            client.post(
                "/capabilities/shop.api.run", content=b"invalid json"
            ).status_code
            == 422
        )
        assert client.get("/openapi.json").json() == json.loads(
            (tmp_path / "openapi.json").read_bytes()
        )
    assert "shop.admin" not in sys.modules
    assert sys.modules["shop"].__doc__ == "A real package initializer."


def test_mcp_sync_async_listing_unknown_and_invalid(tmp_path, inputs):
    bundle(tmp_path, inputs, "mcp")
    server = create_server(tmp_path)

    async def check():
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            assert {t.name for t in tools} == {
                "shop.api.run",
                "shop.pricing.run",
                "shop.inventory.available",
            }
            assert all(
                t.meta["sh.outerspace.apizr/capability-id"].startswith("python:shop.")
                for t in tools
            )
            assert (await client.call_tool("shop.api.run", {})).structured_content == 7
            assert (
                await client.call_tool("shop.pricing.run", {"x": 4})
            ).structured_content == 5
            assert (await client.call_tool("shop.api.run", {"x": "bad"})).is_error
            assert (await client.call_tool("shop.api.helper", {})).is_error

    anyio.run(check)
    assert "shop.admin" not in sys.modules


@pytest.mark.parametrize("interface", ["rest", "mcp"])
@pytest.mark.parametrize(
    "body", ["raise RuntimeError('SECRET /host/private')", "return float('nan')"]
)
def test_execution_failure_sanitized(tmp_path, interface, body):
    values = evidence(
        {"isolated.py": ("def f(): " + body).encode()}, selected=("python:isolated:f",)
    )
    bundle(tmp_path, values, interface)
    if interface == "rest":
        with TestClient(create_app(tmp_path)) as client:
            result = client.post("/capabilities/isolated.f", json={})
            assert result.status_code == 500 and result.json() == {
                "detail": "Internal server error"
            }
    else:

        async def check():
            async with Client(create_server(tmp_path)) as client:
                result = await client.call_tool("isolated.f", {})
                assert (
                    result.is_error
                    and result.content[0].text == "Tool execution failed"
                )

        anyio.run(check)


@pytest.mark.parametrize("interface", ["rest", "mcp"])
def test_persistent_direct_state(tmp_path, interface):
    values = evidence(
        {"isolated.py": b"def f(x: list[int] = []):\n    x.append(1)\n    return x\n"},
        selected=("python:isolated:f",),
    )
    bundle(tmp_path, values, interface)
    if interface == "rest":
        with TestClient(create_app(tmp_path)) as client:
            assert client.post("/capabilities/isolated.f", json={}).json() == [1]
            assert client.post("/capabilities/isolated.f", json={}).json() == [1, 1]
    else:

        async def check():
            async with Client(create_server(tmp_path)) as client:
                assert (
                    await client.call_tool("isolated.f", {})
                ).structured_content == [1]
                assert (
                    await client.call_tool("isolated.f", {})
                ).structured_content == [1, 1]

        anyio.run(check)


@pytest.mark.parametrize(
    "name",
    [
        "source/shop/api.py",
        "source/shop/admin.py",
        "source/shop/__init__.py",
        "capability-catalog.json",
        "capability-graph.json",
        "repository-readiness.json",
        "exposure-plan.json",
        "exposure-policy.json",
        "openapi.json",
    ],
)
def test_tampered_artifacts_fail_before_any_import(tmp_path, inputs, name):
    bundle(tmp_path, inputs, "rest")
    (tmp_path / name).write_bytes(b"SECRET /host/private")
    with pytest.raises(IntegrityError, match="^Repository bundle startup failed$"):
        create_app(tmp_path)
    assert "shop" not in sys.modules


@pytest.mark.parametrize(
    "field", ["source_digest", "bundle_path", "size", "module", "is_package"]
)
def test_manifest_source_tampering(tmp_path, inputs, field):
    artifacts = bundle(tmp_path, inputs, "rest")
    manifest = json.loads(artifacts["apizr-repository-rest.json"])
    manifest["sources"][0][field] = "forged"
    (tmp_path / "apizr-repository-rest.json").write_text(json.dumps(manifest))
    with pytest.raises(IntegrityError):
        create_app(tmp_path)


def test_binding_failure_cleans_all_imports(tmp_path, inputs, monkeypatch):
    import apizr.repository_interfaces.runtime as runtime

    bundle(tmp_path, inputs, "rest")

    def fail(*args):
        raise RuntimeError("SECRET")

    monkeypatch.setattr(runtime, "verify_binding", fail)
    with pytest.raises(IntegrityError):
        create_app(tmp_path)
    assert "shop" not in sys.modules


def loader_fixture(root, *, package=True):
    """Exercise loader independently: Readiness v1 does not permit these imports."""
    sources = {
        "pkg.api": b"from .helpers import helper\ndef run(): return helper()\n",
        "pkg.helpers": b"def helper(): return 42\n",
        "pkg.unrelated": b"raise RuntimeError('unrelated executed')\n",
    }
    if package:
        sources["pkg"] = b"from . import helpers\nINITIALIZED = True\n"
    entries = []
    for module, content in sources.items():
        path = (
            "source/"
            + module.replace(".", "/")
            + ("/__init__.py" if module == "pkg" else ".py")
        )
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)
        entries.append(
            {
                "module": module,
                "bundle_path": path,
                "source_digest": digest(content),
                "size": len(content),
                "is_package": module == "pkg",
            }
        )
    return RepositoryLoader(root, entries)


@pytest.mark.parametrize("package", [True, False])
def test_verified_relative_imports_real_and_namespace_packages(tmp_path, package):
    loader = loader_fixture(tmp_path, package=package)
    loader.install()
    module = importlib.import_module("pkg.api")
    assert module.run() == 42
    assert importlib.import_module("pkg.api") is module
    assert "pkg.unrelated" not in sys.modules
    if package:
        assert sys.modules["pkg"].INITIALIZED is True
    else:
        assert not (tmp_path / "source/pkg/__init__.py").exists()
    assert loader.find_spec("external_unmanaged") is None
    with pytest.raises(ImportError, match="outside repository manifest"):
        importlib.import_module("pkg.unlisted")


@pytest.mark.parametrize("target", ["api.py", "helpers.py", "__init__.py"])
def test_loader_tampering_at_import_time(tmp_path, target):
    loader = loader_fixture(tmp_path)
    loader.install()
    marker = tmp_path / "EXECUTED"
    (tmp_path / "source/pkg" / target).write_text(
        f"open({str(marker)!r}, 'w').write('bad')\n"
    )
    with pytest.raises(IntegrityError):
        importlib.import_module("pkg.api")
    assert not marker.exists()


def test_cached_namespace_conflict_and_tree_contradiction(
    tmp_path, inputs, monkeypatch
):
    bundle(tmp_path, inputs, "rest")
    monkeypatch.setitem(sys.modules, "shop", types.ModuleType("shop"))
    with pytest.raises(IntegrityError):
        create_app(tmp_path)
    with pytest.raises(IntegrityError, match="Contradictory"):
        RepositoryLoader(
            tmp_path,
            [
                {"module": "a", "is_package": False},
                {"module": "a.b", "is_package": False},
            ],
        )


def test_namespace_bundle_end_to_end(tmp_path):
    values = evidence(
        {"ns/deep/api.py": b"def run(): return 1\n"},
        selected=("python:ns.deep.api:run",),
    )
    bundle(tmp_path, values, "rest")
    with TestClient(create_app(tmp_path)) as client:
        assert client.post("/capabilities/ns.deep.api.run", json={}).json() == 1


@pytest.mark.parametrize("value", [None, True, "s", 3, 2.5, [1, False], {"a": [None]}])
def test_finite_result_semantics(value):
    assert result_value(value) == value


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), {1: "a"}, object(), (1, 2), {1, 2}]
)
def test_non_json_outputs_refused(value):
    with pytest.raises(ValueError):
        result_value(value)


@pytest.mark.parametrize("interface", ["rest", "mcp"])
@pytest.mark.parametrize("package", [True, False])
def test_validated_cross_module_support_without_exposing_helper(
    tmp_path, interface, package
):
    sources = {
        "pkg/api.py": b"def public(): return helper()\ndef helper():\n    from .pricing import calculate\n    return calculate()\n",
        "pkg/pricing.py": b"def calculate(): return 42\n",
        "pkg/admin.py": b"raise RuntimeError('UNRELATED')\n",
    }
    if package:
        sources["pkg/__init__.py"] = b"from . import pricing\nINITIALIZED = True\n"
    inputs = evidence(sources, selected=("python:pkg.api:public",))
    artifacts = bundle(tmp_path, inputs, interface)
    # This is real upstream eligibility, not a model_copy readiness override.
    assert inputs[4].capability_ids() == ("python:pkg.api:public",)
    if interface == "rest":
        with TestClient(create_app(tmp_path)) as client:
            assert client.post("/capabilities/pkg.api.public", json={}).json() == 42
            assert (
                client.post("/capabilities/pkg.pricing.calculate", json={}).status_code
                == 404
            )
    else:

        async def check():
            async with Client(create_server(tmp_path)) as client:
                assert [t.name for t in (await client.list_tools()).tools] == [
                    "pkg.api.public"
                ]
                assert (
                    await client.call_tool("pkg.api.public", {})
                ).structured_content == 42

        anyio.run(check)
    assert "pkg.pricing" in sys.modules and "pkg.admin" not in sys.modules
    assert "source/pkg/pricing.py" in artifacts


def test_support_changed_after_startup_but_before_lazy_import(tmp_path):
    sources = {
        "pkg/api.py": b"def public(): return helper()\ndef helper():\n    from .pricing import calculate\n    return calculate()\n",
        "pkg/pricing.py": b"def calculate(): return 42\n",
    }
    bundle(tmp_path, evidence(sources, selected=("python:pkg.api:public",)), "rest")
    app = create_app(tmp_path)
    assert "pkg.pricing" not in sys.modules
    marker = tmp_path / "TAMPERED"
    (tmp_path / "source/pkg/pricing.py").write_text(
        f"open({str(marker)!r}, 'w').write('BAD')"
    )
    with TestClient(app) as client:
        assert client.post("/capabilities/pkg.api.public", json={}).json() == {
            "detail": "Internal server error"
        }
    assert not marker.exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "self_hash",
        "interface_digest",
        "interface_schema",
        "target",
        "catalog_binding",
        "plan_binding",
        "policy_binding",
        "repository_binding",
        "direct",
        "empty",
        "source_universe",
        "source_evidence",
        "source_path",
        "selection",
        "transport_count",
        "identity",
        "invocation",
        "route",
    ],
)
def test_semantic_manifest_and_evidence_tampering(tmp_path, inputs, mutation):
    artifacts = bundle(tmp_path, inputs, "rest")
    manifest = json.loads(artifacts["apizr-repository-rest.json"])
    contract = json.loads(artifacts["repository-interface.json"])
    exposure = json.loads(artifacts["exposure-plan.json"])
    forged = digest(b"forged")
    if mutation == "schema":
        manifest["schema_version"] = "apizr.rest/v1"
    elif mutation == "self_hash":
        manifest["artifacts"]["apizr-repository-rest.json"] = forged
    elif mutation == "interface_digest":
        manifest["repository_interface_digest"] = forged
    elif mutation == "interface_schema":
        contract["schema_version"] = "wrong"
    elif mutation == "target":
        contract["interface"] = "mcp"
    elif mutation == "catalog_binding":
        contract["catalog_digest"] = forged
    elif mutation == "plan_binding":
        manifest["exposure_plan_digest"] = forged
    elif mutation == "policy_binding":
        exposure["exposure_policy_digest"] = forged
    elif mutation == "repository_binding":
        contract["repository_digest"] = forged
    elif mutation == "direct":
        exposure["capabilities"][0]["compatible_execution_modes"] = ["oci-container"]
    elif mutation == "empty":
        exposure["capabilities"] = []
    elif mutation == "source_universe":
        contract["sources"].pop()
        manifest["sources"] = contract["sources"]
    elif mutation == "source_evidence":
        contract["sources"][0]["size"] += 1
        manifest["sources"] = contract["sources"]
    elif mutation == "source_path":
        contract["sources"][0]["bundle_path"] = "../outside"
        manifest["sources"] = contract["sources"]
    elif mutation == "selection":
        contract["capabilities"].pop()
    elif mutation == "transport_count":
        manifest["endpoints"].pop()
    elif mutation == "identity":
        contract["capabilities"][0]["public_name"] = "forged"
    elif mutation == "invocation":
        manifest["endpoints"][0]["execution"] = "async"
    else:
        manifest["endpoints"][0]["route"] = "/capabilities/forged"
    # Updating artifact hashes alone must not bypass cross-artifact evidence checks.
    exposure_bytes = json.dumps(exposure).encode()
    if mutation in {"policy_binding", "direct", "empty"}:
        (tmp_path / "exposure-plan.json").write_bytes(exposure_bytes)
        manifest["artifacts"]["exposure-plan.json"] = digest(exposure_bytes)
        contract["exposure_plan_digest"] = digest(exposure_bytes)
        manifest["exposure_plan_digest"] = digest(exposure_bytes)
    contract_bytes = json.dumps(contract).encode()
    (tmp_path / "repository-interface.json").write_bytes(contract_bytes)
    manifest["artifacts"]["repository-interface.json"] = digest(contract_bytes)
    if mutation != "interface_digest":
        manifest["repository_interface_digest"] = digest(contract_bytes)
    (tmp_path / "apizr-repository-rest.json").write_text(json.dumps(manifest))
    with pytest.raises(IntegrityError, match="^Repository bundle startup failed$"):
        create_app(tmp_path)
    assert "shop" not in sys.modules


def test_entry_point_pin_and_symlink_artifact_refusal(tmp_path, inputs):
    from apizr.repository_interfaces.runtime import load_bundle, read_artifact

    bundle(tmp_path, inputs, "rest")
    with pytest.raises(IntegrityError):
        load_bundle(tmp_path, "rest", digest(b"wrong pin"))
    file = tmp_path / "source/shop/api.py"
    file.unlink()
    file.symlink_to(tmp_path / "source/shop/pricing.py")
    with pytest.raises(IntegrityError):
        create_app(tmp_path)
    with pytest.raises(IntegrityError):
        read_artifact(tmp_path, "../outside")


@pytest.mark.parametrize(
    "field", ["tool_name", "input_schema", "description", "protocol"]
)
def test_mcp_manifest_presentation_cannot_drift_from_evidence(tmp_path, inputs, field):
    artifacts = bundle(tmp_path, inputs, "mcp")
    manifest = json.loads(artifacts["apizr-repository-mcp.json"])
    if field == "protocol":
        manifest["protocol"]["target"] = "forged"
    else:
        manifest["tools"][0][field] = {} if field == "input_schema" else "forged"
    (tmp_path / "apizr-repository-mcp.json").write_text(json.dumps(manifest))
    with pytest.raises(IntegrityError):
        create_server(tmp_path)


def test_mcp_hash_fallback_at_runtime(tmp_path):
    values = evidence({"café.py": b"def f(): return 1\n"}, selected=("python:café:f",))
    artifacts = bundle(tmp_path, values, "mcp")
    name = json.loads(artifacts["mcp-tools.json"])["tools"][0]["name"]

    async def check():
        async with Client(create_server(tmp_path)) as client:
            assert (await client.call_tool(name, {})).structured_content == 1

    anyio.run(check)


def test_nonregular_artifact_refused_without_blocking(tmp_path):
    import os

    from apizr.repository_interfaces.runtime import read_artifact

    os.mkfifo(tmp_path / "fifo")
    with pytest.raises(IntegrityError, match="regular file"):
        read_artifact(tmp_path, "fifo")
