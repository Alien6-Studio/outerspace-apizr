"""Canonical artifacts and schemas, exercised on every supported Python in CI."""

import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from apizr.exposure import ExposurePolicy, plan_exposure
from apizr.graph import analyze_repository
from apizr.repository import ScanPolicy
from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.model import (
    MCPManifest,
    RepositoryInterface,
    RestManifest,
)
from apizr.repository_readiness import RepositoryReadinessPolicy, assess_repository

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "tests/fixtures/repository-interface/v1"


def render(root, interface):
    evidence = analyze_repository(root, scan_policy=ScanPolicy(source_roots=("src",)))
    readiness = assess_repository(
        evidence.catalog,
        evidence.graph,
        policy=RepositoryReadinessPolicy.model_validate(
            {"execution": {"modes": ["direct"]}}
        ),
    )
    policy = ExposurePolicy.model_validate(
        {
            "selection": {
                "include": [
                    "python:shop.api:run",
                    "python:shop.pricing:run",
                    "python:shop.inventory:available",
                ]
            },
            "interfaces": ["rest", "mcp"],
            "execution": {"allowed": ["direct"]},
        }
    )
    exposure = plan_exposure(evidence.catalog, evidence.graph, readiness, policy=policy)
    return render_repository_bundle(
        evidence.catalog,
        evidence.graph,
        readiness,
        policy,
        exposure,
        evidence.sources,
        interface=interface,
    )


@pytest.mark.parametrize("interface", ["rest", "mcp"])
def test_golden_and_relocation(tmp_path, interface):
    shutil.copytree(FIXTURE / "project", tmp_path / "moved")
    original = render(FIXTURE / "project", interface)
    assert render(tmp_path / "moved", interface) == original
    for filename in (
        f"apizr-repository-{interface}.json",
        "repository-interface.json",
        "openapi.json" if interface == "rest" else "mcp-tools.json",
    ):
        assert original[filename] == (FIXTURE / interface / filename).read_bytes()
    assert all(str(tmp_path).encode() not in content for content in original.values())
    assert (
        b"shop.api.quote"
        not in original["openapi.json" if interface == "rest" else "mcp-tools.json"]
    )


@pytest.mark.parametrize(
    "name,model",
    [
        ("repository-interface", RepositoryInterface),
        ("repository-rest", RestManifest),
        ("repository-mcp", MCPManifest),
    ],
)
def test_published_schemas(name, model):
    schema = json.loads((ROOT / f"docs/specs/apizr-{name}-v1.schema.json").read_bytes())
    assert schema == model.model_json_schema()
    Draft202012Validator.check_schema(schema)
    target = "mcp" if name == "repository-mcp" else "rest"
    file = (
        "repository-interface.json"
        if name == "repository-interface"
        else f"apizr-{name}.json"
    )
    value = json.loads((FIXTURE / target / file).read_bytes())
    Draft202012Validator(schema).validate(value)
    assert model.model_validate(value).model_dump(mode="json") == value
