"""Run unchanged on every supported Python: all bundle hashes must agree."""

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from apizr.generators.rest import render
from apizr.inspection import inspect_source

from .helpers import application

FIXTURE = Path(__file__).parents[1] / "fixtures/rest/v1"


def test_reviewed_rest_golden_and_all_artifact_hashes():
    source = (FIXTURE / "pricing.py").read_bytes()
    artifacts = render(inspect_source(source, module_name="golden.pricing"), source)
    for name in ("openapi.json", "apizr-rest.json"):
        assert artifacts[name] == (FIXTURE / name).read_bytes()
    expected = json.loads((FIXTURE / "apizr-rest.json").read_bytes())
    assert set(artifacts) == set(expected["artifacts"]) | {"apizr-rest.json"}
    for name, digest in expected["artifacts"].items():
        assert hashlib.sha256(artifacts[name]).hexdigest() == digest["value"]


def test_golden_contract_serves_sync_async_and_declared_validation(tmp_path):
    source = (FIXTURE / "pricing.py").read_bytes()
    with application(
        tmp_path / "bundle", source, module_name="golden.pricing"
    ) as adapter:
        client = TestClient(adapter.app)
        assert (
            client.post("/capabilities/total", json={"prices": [10, 20]}).json() == 36.0
        )
        assert (
            client.post(
                "/capabilities/total", json={"prices": [10], "currency": "GBP"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/capabilities/greet", json={"name": "Ada", "punctuation": "?"}
            ).json()
            == "Hello Ada?"
        )
        assert client.get("/openapi.json").json() == json.loads(
            (FIXTURE / "openapi.json").read_bytes()
        )
