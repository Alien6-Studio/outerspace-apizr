import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.capabilities.model import Digest
from apizr.execution.policy import BackendCapabilities
from apizr.governed.runtime import GovernedRuntime
from apizr.interfaces.serialization import json_bytes

from .helpers import bundle


def rehash(root, document, bridge):
    # Recompute outer file hashes so these tests reach semantic linkage checks,
    # rather than all passing at the first generic artifact mismatch.
    for name in bridge["artifacts"]:
        bridge["artifacts"][name] = Digest.of_bytes(
            (root / name).read_bytes()
        ).model_dump(mode="json")
    document["artifacts"] = {**bridge["artifacts"]}
    raw = json_bytes(bridge)
    (root / "execution/bundle.json").write_bytes(raw)
    document["artifacts"]["execution/bundle.json"] = Digest.of_bytes(raw).model_dump(
        mode="json"
    )
    (root / "apizr-rest.json").write_bytes(json_bytes(document))


@pytest.mark.parametrize(
    "fault",
    [
        "manifest_type",
        "bridge_digest",
        "bridge_type",
        "missing_worker",
        "policy_digest",
        "contract_digest",
        "plan_digest",
        "interface",
        "source_link",
        "inspection_link",
        "capability_set",
        "backend",
    ],
)
def test_startup_checks_content_linkage_not_only_file_hashes(tmp_path, fault):
    root = bundle(tmp_path / "bundle", "rest", source=b"def f(x: int=1): return x")
    document = json.loads((root / "apizr-rest.json").read_bytes())
    bridge = json.loads((root / "execution/bundle.json").read_bytes())
    identity = next(iter(bridge["capabilities"]))
    if fault == "manifest_type":
        document["schema_version"] = "apizr.mcp/v1"
    elif fault == "bridge_digest":
        pass
    elif fault == "bridge_type":
        bridge["transport"] = "mcp"
    elif fault == "missing_worker":
        bridge["artifacts"].pop("execution/worker.py")
    elif fault == "policy_digest":
        bridge["policy_digest"]["value"] = "0" * 64
    elif fault == "contract_digest":
        bridge["contract_digest"]["value"] = "0" * 64
    elif fault == "plan_digest":
        bridge["capabilities"][identity]["digest"]["value"] = "0" * 64
    elif fault == "interface":
        document["capabilities"][0]["description"] = "different contract"
        bridge["contract_digest"] = Digest.of_bytes(
            json_bytes(document["capabilities"])
        ).model_dump(mode="json")
    elif fault == "source_link":
        document["ir_digest"]["value"] = "0" * 64
    elif fault == "inspection_link":
        (root / "readiness.json").write_bytes(
            (root / "readiness.json").read_bytes() + b" "
        )
    elif fault == "capability_set":
        bridge["capabilities"]["python:other:f"] = bridge["capabilities"][identity]
    elif fault == "backend":
        bridge["backend_version"] = "apizr.future/v1"
    rehash(root, document, bridge)
    if fault == "bridge_digest":
        document = json.loads((root / "apizr-rest.json").read_bytes())
        document["artifacts"]["execution/bundle.json"]["value"] = "0" * 64
        (root / "apizr-rest.json").write_bytes(json_bytes(document))
    with pytest.raises(RuntimeError, match="bundle unavailable or invalid"):
        GovernedRuntime(root, "rest")


def test_post_startup_manifest_or_host_change_fails_call(tmp_path, monkeypatch):
    root = bundle(tmp_path / "bundle", "rest", source=b"def f(): return 1")
    runtime = GovernedRuntime(root, "rest")
    monkeypatch.setattr(
        "apizr.governed.runtime.local_capabilities",
        lambda: BackendCapabilities(available=False),
    )
    assert runtime.invoke("python:governed_sample:f", {}).status == "policy_refused"
    monkeypatch.undo()
    path = root / "apizr-rest.json"
    path.write_bytes(path.read_bytes() + b" ")
    assert runtime.invoke("python:governed_sample:f", {}).status == "binding_failed"


@settings(max_examples=5, deadline=None)
@given(st.binary(min_size=1, max_size=30))
def test_tampering_property(tmp_path_factory, mutation):
    root = bundle(
        tmp_path_factory.mktemp("mutant") / "bundle",
        "rest",
        source=b"def f(): return 1",
    )
    runtime = GovernedRuntime(root, "rest")
    path = root / "source/governed_sample.py"
    path.write_bytes(path.read_bytes() + mutation)
    assert runtime.invoke("python:governed_sample:f", {}).status == "binding_failed"
