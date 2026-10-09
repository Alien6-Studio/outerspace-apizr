import json
import sys

import pytest
from fastapi.testclient import TestClient
from governed_repository.helpers import bundle
from repository_interfaces.conftest import evidence

from apizr.client_collections.planner import plan_client_collection
from apizr.execution.policy import ExecutionPolicy
from apizr.governed_repository.rest import create_app
from apizr.governed_repository.runtime import GovernedRuntime
from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.output import write_bundle

from .test_runtime import INVALID_NESTED
from .test_static import NESTED

SOURCE = (
    NESTED.replace(
        'return payload["features"]["age"] * payload["features"]["score"]',
        'return helper(payload["features"]["age"], payload["features"]["score"])',
    )
    + "\ndef helper(age, score): return age * score\n"
)
FILES = {
    "typed.py": SOURCE.encode(),
    "experimental.py": b"@unknown\ndef broken(): yield 1\n",
}
SELECTED = ["python:typed:predict"]
PAYLOAD = {"payload": {"customer_id": "c", "features": {"age": 2, "score": 3}}}


@pytest.mark.parametrize("interface", ["rest", "mcp"])
def test_repository_selected_structured_contract_preserves_global_audit(
    tmp_path, interface
):
    inputs = evidence(FILES, selected=SELECTED)
    catalog, graph, readiness, policy, exposure, sources = inputs
    assert graph.complete
    unrelated = next(
        a for a in readiness.assessments if a.capability_id.endswith(":broken")
    )
    assert not unrelated.local_readiness.can_generate_interface
    artifacts = render_repository_bundle(*inputs, interface=interface)
    contract = json.loads(artifacts["repository-interface.json"])
    assert [c["capability_id"] for c in contract["capabilities"]] == SELECTED
    shape = contract["capabilities"][0]["invocation"]["parameters"][0]["type"]
    assert shape["kind"] == "object" and any(
        f["name"] == "features" and f["type"]["kind"] == "object"
        for f in shape["fields"]
    )
    assert "python:typed:helper" in json.dumps(exposure.model_dump())
    if interface == "rest":
        root = tmp_path / "rest"
        write_bundle(root, artifacts)
        assert plan_client_collection(root).requests[0].example == {
            "payload": {"customer_id": "", "features": {"age": 0, "score": 0.0}}
        }


@pytest.mark.parametrize("interface", ["rest", "mcp"])
def test_governed_fresh_process_uses_serialized_object_contract(tmp_path, interface):
    root = bundle(
        tmp_path / "worker",
        interface,
        files=FILES,
        selected=SELECTED,
        policy=ExecutionPolicy(),
    )
    runtime = GovernedRuntime(root, interface)
    for _ in range(2):
        assert runtime.invoke(SELECTED[0], PAYLOAD).value == 6.0
    for invalid in INVALID_NESTED:
        assert (
            runtime.invoke(SELECTED[0], {"payload": invalid}).status == "invalid_input"
        )
    assert "typed" not in sys.modules and "experimental" not in sys.modules
    # The retained contract includes the shape, rather than deriving it in the worker.
    assert b'"kind":"object"' in (root / "repository-interface.json").read_bytes()


def test_governed_rest_real_http(tmp_path):
    root = bundle(tmp_path / "http", files=FILES, selected=SELECTED)
    with TestClient(create_app(root)) as client:
        response = client.post("/capabilities/typed.predict", json=PAYLOAD)
        assert response.status_code == 200 and response.json() == 6.0
        response = client.post("/capabilities/typed.predict", json={"payload": {}})
        assert response.status_code == 422
